import hashlib
from pathlib import Path

import pytest

from src.ingest.dedup_hash import file_sha256


def test_file_sha256_returns_hex_string(tmp_path):
    f = tmp_path / 'sample.bin'
    f.write_bytes(b'hello world')

    result = file_sha256(str(f))

    assert isinstance(result, str)
    assert len(result) == 64  # SHA-256 hex digest is 64 characters
    assert all(c in '0123456789abcdef' for c in result)


def test_file_sha256_is_deterministic(tmp_path):
    f = tmp_path / 'sample.bin'
    f.write_bytes(b'deterministic content')

    assert file_sha256(str(f)) == file_sha256(str(f))


def test_file_sha256_differs_for_different_content(tmp_path):
    f1 = tmp_path / 'a.bin'
    f2 = tmp_path / 'b.bin'
    f1.write_bytes(b'content A')
    f2.write_bytes(b'content B')

    assert file_sha256(str(f1)) != file_sha256(str(f2))


def test_file_sha256_matches_reference_value(tmp_path):
    content = b'hello world'
    f = tmp_path / 'ref.bin'
    f.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert file_sha256(str(f)) == expected


def test_file_sha256_handles_empty_file(tmp_path):
    f = tmp_path / 'empty.bin'
    f.write_bytes(b'')

    result = file_sha256(str(f))

    expected = hashlib.sha256(b'').hexdigest()
    assert result == expected


def test_file_sha256_handles_large_file(tmp_path):
    """Verify chunked reading for files larger than the 1 MB buffer."""
    large_content = b'X' * (2 * 1024 * 1024)  # 2 MB
    f = tmp_path / 'large.bin'
    f.write_bytes(large_content)

    result = file_sha256(str(f))

    expected = hashlib.sha256(large_content).hexdigest()
    assert result == expected
