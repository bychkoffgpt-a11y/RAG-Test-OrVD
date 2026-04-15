import sys
from pathlib import Path

from src.embeddings.client import EmbeddingClient


def test_embed_fallbacks_to_cpu_when_cuda_encode_fails(monkeypatch, tmp_path):
    model_path = tmp_path / 'emb-model'
    model_path.mkdir()
    (model_path / 'config.json').write_text('{}')

    monkeypatch.setattr('src.embeddings.client.settings.embedding_model_path', str(model_path))
    monkeypatch.setattr('src.embeddings.client.settings.embedding_device', 'auto')
    monkeypatch.setattr('src.embeddings.client.EmbeddingClient._resolve_device', lambda _: 'cuda')

    class _FakeVector:
        def __init__(self, values):
            self._values = values

        def tolist(self):
            return self._values

    class _FakeSentenceTransformer:
        def __init__(self, _path, local_files_only, device):
            assert local_files_only is True
            self.device = device

        def encode(self, *_args, **_kwargs):
            if self.device == 'cuda':
                raise RuntimeError('CUDA error: no kernel image is available for execution on the device')
            return _FakeVector([0.11, 0.22, 0.33])

    monkeypatch.setattr('src.embeddings.client.SentenceTransformer', _FakeSentenceTransformer)

    EmbeddingClient._model = None
    EmbeddingClient._device = None

    result = EmbeddingClient.embed('question')

    assert result == [0.11, 0.22, 0.33]
    assert EmbeddingClient._device == 'cpu'


def test_resolve_device_cuda_fallbacks_to_cpu_when_not_strict(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return False

    class _FakeTorch:
        cuda = _FakeCuda()

    monkeypatch.setattr('src.embeddings.client.settings.embedding_device_strict', False)
    monkeypatch.setitem(sys.modules, 'torch', _FakeTorch())

    resolved = EmbeddingClient._resolve_device('cuda')

    assert resolved == 'cpu'


def test_resolve_device_cuda_raises_when_not_available_and_strict(monkeypatch):
    class _FakeCuda:
        @staticmethod
        def is_available():
            return False

    class _FakeTorch:
        cuda = _FakeCuda()

    monkeypatch.setattr('src.embeddings.client.settings.embedding_device_strict', True)
    monkeypatch.setitem(sys.modules, 'torch', _FakeTorch())

    try:
        EmbeddingClient._resolve_device('cuda')
        assert False, 'Ожидалось исключение при строгом режиме CUDA'
    except RuntimeError as exc:
        assert 'no CUDA device is available' in str(exc)
