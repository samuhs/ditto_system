"""Shared guard against oversized file uploads (#25).

nginx enforces `client_max_body_size` in front of the API (`make up`), but
`make up-local` exposes uvicorn directly with no proxy in front of it, so the
API must bound uploads itself. `read_upload` reads a file in bounded chunks
and refuses with 413 as soon as the configured limit is crossed, so an
oversized upload is never buffered in memory.
"""
from fastapi import HTTPException, UploadFile

from app.core.config.settings import get_settings

_CHUNK_SIZE = 1024 * 1024  # 1 MiB: how much of an oversized upload we ever hold at once


def max_upload_bytes() -> int:
    """The configured upload size limit, in bytes (MAX_UPLOAD_SIZE_MB, default 50 MB)."""
    return get_settings().max_upload_size_mb * 1024 * 1024


async def read_upload(file: UploadFile, *, limit_bytes: int | None = None) -> bytes:
    """Read an UploadFile's content, refusing with 413 past the size limit.

    Reads in bounded chunks and aborts the moment the limit is exceeded, instead
    of calling `file.read()` with no bound, so an oversized upload is never fully
    buffered in memory. `limit_bytes` overrides the configured default (tests only).
    """
    limit = max_upload_bytes() if limit_bytes is None else limit_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            name = file.filename or "arquivo"
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{name}: arquivo maior que o limite de "
                    f"{limit // (1024 * 1024)} MB para upload."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)
