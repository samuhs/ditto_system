"""Markdown chunker: one chunk per heading section, prefixed by its heading path."""
import re
from collections.abc import Iterator

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.chunking.base import Chunker, chunking_registry

_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _sections(text: str) -> Iterator[tuple[list[str], str]]:
    """Yield (heading path, body) for every section that has text of its own.

    The path holds the heading lines from the top level down to the section's
    own heading, so a chunk carries the context of the headings above it.
    Lines inside code fences are never taken as headings.
    """
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    in_fence = False

    def flush() -> tuple[list[str], str] | None:
        content = "\n".join(body).strip()
        return ([line for _, line in stack], content) if content else None

    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading is None:
            body.append(line)
            continue
        section = flush()
        if section:
            yield section
        level = len(heading.group(1))
        stack = [entry for entry in stack if entry[0] < level]
        stack.append((level, line.strip()))
        body = []
    section = flush()
    if section:
        yield section


class MarkdownHeaderChunker(Chunker):
    """Cuts at Markdown headings: a chunk never mixes two sections.

    A section longer than `chunk_size` is split recursively, and each piece
    repeats the heading path. Text without headings is split recursively.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def split(self, text: str) -> list[str]:
        """Split text into one chunk per section (or more, if it is too long)."""
        chunks: list[str] = []
        for path, body in _sections(text):
            chunks.extend(self._fit(path, body))
        return chunks

    def _fit(self, path: list[str], body: str) -> list[str]:
        """The section as one chunk, or as pieces that each fit with the path."""
        prefix = "".join(f"{line}\n" for line in path)
        if len(prefix) + len(body) <= self._chunk_size:
            return [prefix + body]
        budget = max(self._chunk_size - len(prefix), 1)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=budget,
            chunk_overlap=min(self._chunk_overlap, budget // 2),
        )
        return [prefix + piece for piece in splitter.split_text(body)]


chunking_registry.register("markdown", MarkdownHeaderChunker)
