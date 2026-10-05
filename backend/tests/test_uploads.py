"""Tests for the shared upload-size guard (app.core.uploads)."""
import asyncio
import io

from fastapi import HTTPException, UploadFile

from app.core.config.settings import get_settings
from app.core.uploads import max_upload_bytes, read_upload


def _upload(data: bytes, filename: str = "f.txt") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


def test_read_upload_accepts_file_at_the_limit():
    data = b"a" * 10
    content = asyncio.run(read_upload(_upload(data), limit_bytes=10))
    assert content == data


def test_read_upload_rejects_file_over_the_limit():
    data = b"a" * 11
    try:
        asyncio.run(read_upload(_upload(data, filename="perguntas.csv"), limit_bytes=10))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 413
        assert "perguntas.csv" in exc.detail
        assert "MB" in exc.detail


def test_read_upload_never_buffers_past_the_limit():
    """A giant upload must be refused after only a few bytes beyond the limit are seen."""
    chunk_calls: list[int] = []

    class _TrackingFile:
        def __init__(self, total: int) -> None:
            self._remaining = total

        def read(self, size: int = -1) -> bytes:
            chunk_calls.append(size)
            take = min(size, self._remaining)
            self._remaining -= take
            return b"a" * take

    upload = UploadFile(file=io.BytesIO(b""), filename="huge.csv")
    upload.file = _TrackingFile(10 * 1024 * 1024 * 1024)  # 10 GiB, never fully read

    try:
        asyncio.run(read_upload(upload, limit_bytes=1024))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 413
    # Stopped well short of the declared 10 GiB.
    assert sum(chunk_calls) < 10 * 1024 * 1024


def test_max_upload_bytes_defaults_to_50mb(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_SIZE_MB", raising=False)
    get_settings.cache_clear()
    try:
        assert max_upload_bytes() == 50 * 1024 * 1024
    finally:
        get_settings.cache_clear()


def test_max_upload_bytes_reads_env_override(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "5")
    get_settings.cache_clear()
    try:
        assert max_upload_bytes() == 5 * 1024 * 1024
    finally:
        get_settings.cache_clear()
