import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest

from src.ingest.parsers.doc_converter import convert_doc_to_docx


def test_convert_doc_to_docx_runs_soffice_with_correct_args(tmp_path):
    doc_file = tmp_path / 'report.doc'
    doc_file.write_bytes(b'fake doc')

    with patch('subprocess.run') as mock_run:
        convert_doc_to_docx(str(doc_file))

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert cmd[0] == 'soffice'
    assert '--headless' in cmd
    assert '--convert-to' in cmd
    assert 'docx' in cmd
    assert '--outdir' in cmd
    assert str(tmp_path) in cmd
    assert str(doc_file) in cmd
    assert kwargs.get('check') is True


def test_convert_doc_to_docx_returns_expected_output_path(tmp_path):
    doc_file = tmp_path / 'report.doc'
    doc_file.write_bytes(b'fake doc')

    with patch('subprocess.run'):
        result = convert_doc_to_docx(str(doc_file))

    expected = str(tmp_path / 'report.docx')
    assert result == expected


def test_convert_doc_to_docx_preserves_stem_for_names_with_dots(tmp_path):
    doc_file = tmp_path / 'my.report.v2.doc'
    doc_file.write_bytes(b'x')

    with patch('subprocess.run'):
        result = convert_doc_to_docx(str(doc_file))

    assert result == str(tmp_path / 'my.report.v2.docx')


def test_convert_doc_to_docx_raises_on_soffice_failure(tmp_path):
    doc_file = tmp_path / 'bad.doc'
    doc_file.write_bytes(b'x')

    with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'soffice')):
        with pytest.raises(subprocess.CalledProcessError):
            convert_doc_to_docx(str(doc_file))
