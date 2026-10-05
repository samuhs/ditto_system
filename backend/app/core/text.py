"""Shared text normalization for comparing spellings across the system.

Used by the Grafo de conhecimento (consolidating entities, classifying extracted
types) and by the Experiments API (lenient name comparison, safe filenames), so
a single implementation stays correct for all of them.
"""
import unicodedata


def strip_accents(text: str) -> str:
    """Unicode NFKD decomposition with combining marks (accents) dropped; case unchanged.

    "Árvore" -> "Arvore". Casefold first to also ignore case:
    strip_accents("Árvore".casefold()) -> "arvore".
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
