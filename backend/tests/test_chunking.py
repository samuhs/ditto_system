"""Tests for chunking strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

_TEXT = (
    "First paragraph about the city center and the main square.\n\n"
    "Second paragraph about food, restaurants and local cuisine.\n\n"
    "Third paragraph about transport, taxis and walking around town."
)


def test_fixed_chunker_respects_size():
    chunker = FixedSizeChunker(chunk_size=40, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert all(len(c) <= 60 for c in chunks)


def test_recursive_chunker_produces_chunks():
    chunker = RecursiveChunker(chunk_size=50, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert "".join(chunks).replace(" ", "").replace("\n", "") != ""


def test_token_chunker_produces_chunks():
    chunker = TokenChunker(chunk_size=8, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1


def test_chunkers_registered_and_built():
    assert {"fixed", "recursive", "token"} <= set(chunking_registry.names())
    chunker = build_chunker("recursive", chunk_size=50, chunk_overlap=0)
    assert isinstance(chunker, Chunker)
    assert len(chunker.split(_TEXT)) > 1


_MARKDOWN = (
    "# Guia da cidade\n"
    "Informações de outubro de 2025.\n\n"
    "## Perguntas\n\n"
    "### Onde fica o centro?\n"
    "O centro fica ao redor da Praça da Matriz.\n\n"
    "### Onde comer?\n"
    "Na Rua da Gastronomia:\n\n"
    "- doces;\n"
    "- queijos.\n"
)


def test_markdown_chunker_gives_one_chunk_per_section():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    chunks = MarkdownHeaderChunker().split(_MARKDOWN)
    assert len(chunks) == 3
    assert chunks[0] == "# Guia da cidade\nInformações de outubro de 2025."
    # A section keeps its own heading and every line under it, lists included.
    assert "### Onde comer?" in chunks[2]
    assert chunks[2].endswith("- doces;\n- queijos.")
    assert "Praça da Matriz" not in chunks[2]


def test_markdown_chunker_prefixes_the_heading_path():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    chunks = MarkdownHeaderChunker().split(_MARKDOWN)
    assert chunks[1] == (
        "# Guia da cidade\n## Perguntas\n### Onde fica o centro?\n"
        "O centro fica ao redor da Praça da Matriz."
    )


def test_markdown_chunker_skips_headings_without_body():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    # "## Perguntas" has no text of its own: it survives only as context.
    chunks = MarkdownHeaderChunker().split(_MARKDOWN)
    assert not any(c.endswith("## Perguntas") for c in chunks)


def test_markdown_chunker_splits_long_sections_and_repeats_the_heading():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    body = "\n\n".join(f"Parágrafo {i} " + "texto " * 30 for i in range(6))
    chunks = MarkdownHeaderChunker(chunk_size=300, chunk_overlap=0).split(
        f"### Seção longa\n{body}"
    )
    assert len(chunks) > 1
    assert all(c.startswith("### Seção longa\n") for c in chunks)
    assert all(len(c) <= 300 for c in chunks)


def test_markdown_chunker_keeps_text_before_the_first_heading():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    chunks = MarkdownHeaderChunker().split("Texto solto.\n\n### Título\nCorpo.")
    assert chunks == ["Texto solto.", "### Título\nCorpo."]


def test_markdown_chunker_ignores_hashes_inside_code_fences():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    text = "### Código\n```bash\n# comentário\necho oi\n```"
    assert MarkdownHeaderChunker().split(text) == [text]


def test_markdown_chunker_on_plain_text_falls_back_to_recursive():
    from app.core.chunking.markdown import MarkdownHeaderChunker

    chunks = MarkdownHeaderChunker(chunk_size=50, chunk_overlap=0).split(_TEXT)
    assert len(chunks) > 1
    assert all(len(c) <= 50 for c in chunks)


def test_markdown_chunker_registered():
    assert "markdown" in chunking_registry.names()
    assert build_chunker("markdown").split("### A\nb") == ["### A\nb"]
