"""Tests for the shared accent-stripping text normalization."""
import unicodedata

from app.core.text import strip_accents


def test_removes_common_accents():
    assert strip_accents("árvore") == "arvore"
    assert strip_accents("café") == "cafe"


def test_removes_cedilla():
    assert strip_accents("organização") == "organizacao"


def test_case_is_unchanged():
    assert strip_accents("Árvore") == "Arvore"
    assert strip_accents("ÁRVORE") == "ARVORE"


def test_casefold_before_stripping_also_ignores_case():
    assert strip_accents("Árvore".casefold()) == "arvore"


def test_non_accented_text_is_unchanged():
    assert strip_accents("parque") == "parque"
    assert strip_accents("Parque 23") == "Parque 23"


def test_handles_precomposed_and_decomposed_input_the_same():
    precomposed = "café"  # "e" + U+0301 COMBINING ACUTE ACCENT, composed by the editor into é
    decomposed = "café"  # the same word spelled with an explicit combining accent
    assert unicodedata.normalize("NFC", precomposed) != decomposed  # sanity: differ as strings
    assert strip_accents(precomposed) == strip_accents(decomposed) == "cafe"


def test_empty_string():
    assert strip_accents("") == ""
