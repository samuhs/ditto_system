"""Corpus statistics (document frequencies) for pre-retrieval signals such as IDF."""
import math
from dataclasses import dataclass, field

from app.core.evaluation.overlap_metrics import normalize_pt_tokens


@dataclass
class CorpusStats:
    """Document frequency of each normalised token over a list of texts (chunks)."""

    n_docs: int
    doc_freq: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_texts(cls, texts: list[str]) -> "CorpusStats":
        doc_freq: dict[str, int] = {}
        for text in texts:
            for token in set(normalize_pt_tokens(text)):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        return cls(n_docs=len(texts), doc_freq=doc_freq)

    def idf(self, token: str) -> float:
        """Smoothed IDF, log((N + 1) / (df + 1)); a token absent from the corpus is maximal."""
        return math.log((self.n_docs + 1) / (self.doc_freq.get(token, 0) + 1))


_cache: dict[tuple[str, int], CorpusStats] = {}


def corpus_stats_for_base(store, base: str) -> CorpusStats | None:
    """Stats over the chunks of one indexed variant of the base; None if it has none.

    Every variant holds the same text, cut differently, so the first collection
    (by name) is used: IDF then counts that chunking's chunks as documents.
    Cached per collection and size, so re-ingesting refreshes it.
    """
    prefix = f"{base}__"
    names = sorted(n for n in store.list_collections() if n.startswith(prefix))
    if not names:
        return None
    name = names[0]
    size = store.count(name)
    key = (name, size)
    if key not in _cache:
        points = store.scroll(name, limit=max(size, 1))
        texts = [p["payload"].get("text", "") for p in points]
        _cache[key] = CorpusStats.from_texts(texts)
    return _cache[key]
