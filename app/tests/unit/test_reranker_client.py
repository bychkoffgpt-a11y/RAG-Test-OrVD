from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest

from src.reranker.client import RerankerClient, _is_cuda_runtime_error


# ---------------------------------------------------------------------------
# Reset the class-level model singleton between tests to ensure isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_reranker_singleton():
    old_model = RerankerClient._model
    RerankerClient._model = None
    yield
    RerankerClient._model = old_model


# ---------------------------------------------------------------------------
# _is_cuda_runtime_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('message,expected', [
    ('cuda error: device-side assert triggered', True),
    ('no kernel image is available for execution on the device', True),
    ('device-side assert triggered', True),
    ('RuntimeError: CUDA error', True),
    ('Connection refused', False),
    ('FileNotFoundError', False),
    ('', False),
])
def test_is_cuda_runtime_error_detects_known_patterns(message, expected):
    exc = RuntimeError(message)
    assert _is_cuda_runtime_error(exc) is expected


# ---------------------------------------------------------------------------
# _resolve_device
# ---------------------------------------------------------------------------

def test_resolve_device_cpu_always_returns_cpu():
    assert RerankerClient._resolve_device('cpu') == 'cpu'


def test_resolve_device_invalid_raises_value_error():
    with pytest.raises(ValueError, match='Unsupported reranker device'):
        RerankerClient._resolve_device('tpu')


def test_resolve_device_auto_falls_back_to_cpu_when_torch_unavailable(monkeypatch):
    monkeypatch.setitem(__builtins__ if isinstance(__builtins__, dict) else vars(__builtins__), 'import', None)

    with patch.dict('sys.modules', {'torch': None}):
        device = RerankerClient._resolve_device('auto')

    assert device == 'cpu'


def test_resolve_device_cuda_raises_when_torch_unavailable():
    with patch.dict('sys.modules', {'torch': None}):
        with pytest.raises(RuntimeError, match='torch is unavailable'):
            RerankerClient._resolve_device('cuda')


def test_resolve_device_cuda_raises_when_no_cuda_device():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch.dict('sys.modules', {'torch': mock_torch}):
        with pytest.raises(RuntimeError, match='no CUDA device is available'):
            RerankerClient._resolve_device('cuda')


def test_resolve_device_cuda_returns_cuda_when_available():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    with patch.dict('sys.modules', {'torch': mock_torch}):
        device = RerankerClient._resolve_device('cuda')

    assert device == 'cuda'


def test_resolve_device_auto_uses_cuda_when_available():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    with patch.dict('sys.modules', {'torch': mock_torch}):
        device = RerankerClient._resolve_device('auto')

    assert device == 'cuda'


def test_resolve_device_auto_uses_cpu_when_cuda_unavailable():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch.dict('sys.modules', {'torch': mock_torch}):
        device = RerankerClient._resolve_device('auto')

    assert device == 'cpu'


# ---------------------------------------------------------------------------
# model() — lazy loading
# ---------------------------------------------------------------------------

def test_model_raises_file_not_found_when_config_missing(monkeypatch, tmp_path):
    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))

    with pytest.raises(FileNotFoundError, match='config.json'):
        RerankerClient.model()


def test_model_loads_cross_encoder_when_config_present(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')

    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))
    monkeypatch.setattr('src.reranker.client.settings.reranker_device', 'cpu')

    fake_model = MagicMock()
    with patch('src.reranker.client.CrossEncoder', return_value=fake_model) as mock_ce:
        loaded = RerankerClient.model()

    mock_ce.assert_called_once_with(str(tmp_path), local_files_only=True, device='cpu')
    assert loaded is fake_model
    assert RerankerClient._model is fake_model


def test_model_is_cached_after_first_load(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')

    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))
    monkeypatch.setattr('src.reranker.client.settings.reranker_device', 'cpu')

    fake_model = MagicMock()
    with patch('src.reranker.client.CrossEncoder', return_value=fake_model) as mock_ce:
        first = RerankerClient.model()
        second = RerankerClient.model()

    assert first is second
    mock_ce.assert_called_once()


# ---------------------------------------------------------------------------
# rerank()
# ---------------------------------------------------------------------------

def test_rerank_returns_empty_list_for_no_documents():
    result = RerankerClient.rerank('query', [])
    assert result == []


def test_rerank_calls_model_predict_and_returns_floats(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')

    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))
    monkeypatch.setattr('src.reranker.client.settings.reranker_device', 'cpu')

    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.3]

    with patch('src.reranker.client.CrossEncoder', return_value=fake_model):
        result = RerankerClient.rerank('вопрос', ['doc A', 'doc B'])

    assert result == [0.9, 0.3]
    expected_pairs = [['вопрос', 'doc A'], ['вопрос', 'doc B']]
    fake_model.predict.assert_called_once_with(expected_pairs, show_progress_bar=False)


def test_rerank_falls_back_to_cpu_on_cuda_error(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')

    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))
    monkeypatch.setattr('src.reranker.client.settings.reranker_device', 'cuda')

    gpu_model = MagicMock()
    gpu_model.predict.side_effect = RuntimeError('cuda error: device-side assert triggered')

    cpu_model = MagicMock()
    cpu_model.predict.return_value = [0.5]

    def fake_cross_encoder(path, local_files_only, device):
        return gpu_model if device == 'cuda' else cpu_model

    # _resolve_device('cuda') checks torch.cuda.is_available(); mock it so the test reaches
    # the predict() call where the actual CUDA error and CPU fallback logic is exercised.
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    with patch.dict('sys.modules', {'torch': mock_torch}):
        with patch('src.reranker.client.CrossEncoder', side_effect=fake_cross_encoder):
            result = RerankerClient.rerank('вопрос', ['doc A'])

    assert result == [0.5]
    assert RerankerClient._model is cpu_model


def test_rerank_reraises_non_cuda_error(monkeypatch, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text('{}')

    monkeypatch.setattr('src.reranker.client.settings.reranker_model_path', str(tmp_path))
    monkeypatch.setattr('src.reranker.client.settings.reranker_device', 'cpu')

    bad_model = MagicMock()
    bad_model.predict.side_effect = ValueError('unexpected format')

    with patch('src.reranker.client.CrossEncoder', return_value=bad_model):
        with pytest.raises(ValueError, match='unexpected format'):
            RerankerClient.rerank('вопрос', ['doc A'])
