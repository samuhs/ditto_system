"""Consolidate the chunks' extractions into one Grafo de conhecimento, without an LLM.

- Names: a nickname between parentheses becomes an alias, and the hub's name
  repeated as a suffix ("Cachoeira do Deosdédi em Santo Antônio da Alegria") is
  dropped. The hub is the entity named in most chunks: in a Base about a city it is
  the city, found from the extraction itself, with no configuration and whatever
  the Base is called.
- Entities merge by normalized name, and a name that is another entity's alias
  joins that entity. Type by majority; descriptions concatenated.
- Relations follow their endpoints. An endpoint with no entity line of its own is
  promoted to an entity, unless it holds a digit (a date, time or value, which the
  extractor should not have named): then the relation is dropped.
- Synonymy: entities whose names' vectors have cosine >= 0.8 are linked, never
  merged ("Serra da Lajinha" and "Serra da Laginha"), as in HippoRAG.
"""
import re
import unicodedata
from collections import Counter

import numpy as np

from app.core.graph.knowledge import GraphEntity, GraphRelation, normalize_name

SYNONYM_COSINE = 0.8
# The type of an entity known only as a relation's endpoint.
PROMOTED_TYPE = "outro"
_NICKNAME = re.compile(r"^(.*\S)\s*\(([^()]+)\)\s*$")
# Words that join a name to the hub's when the extractor repeats it as a suffix.
_SUFFIX_JOINERS = {"em", ","}


def _fold(text: str) -> str:
    """Casefolded and without accents, for comparing spellings of the hub."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _split_nicknames(name: str) -> tuple[str, list[str]]:
    """"Cachoeira do Deosdédi (Cachoeira do Dédi)" -> ("Cachoeira do Deosdédi", ["Cachoeira do Dédi"])."""
    aliases = []
    while match := _NICKNAME.match(name):
        name, nickname = match.group(1), match.group(2).strip()
        aliases.insert(0, nickname)
    return " ".join(name.split()), aliases


def _strip_hub(name: str, hub: list[str] | None) -> str:
    """The name without a trailing " em <hub>" or ", <hub>"; never the whole name."""
    if not hub:
        return name
    words = name.split()
    head, tail = words[: -len(hub)], [_fold(w) for w in words[-len(hub):]]
    if tail != hub or not head:
        return name
    if head[-1].endswith(",") and len(head[-1]) > 1:
        return " ".join(head[:-1] + [head[-1][:-1]])
    if _fold(head[-1]) in _SUFFIX_JOINERS and len(head) > 1:
        return " ".join(head[:-1])
    return name


def _hub(occurrences: list[tuple[int, object]]) -> list[str] | None:
    """The folded words of the entity named in most chunks (at least two), if any."""
    chunks: dict[str, set[int]] = {}
    for chunk_id, entity in occurrences:
        base, _ = _split_nicknames(entity.name)
        chunks.setdefault(_fold(normalize_name(base)), set()).add(chunk_id)
    counts = Counter({name: len(ids) for name, ids in chunks.items()})
    if not counts:
        return None
    name, count = counts.most_common(1)[0]
    return name.split() if count >= 2 else None


def _join(texts: list[str]) -> str:
    """Distinct non-empty texts, in order, as one."""
    return " ".join(dict.fromkeys(t for t in texts if t))


def consolidate(extractions: list[dict]) -> tuple[list[GraphEntity], list[GraphRelation]]:
    """Merge the chunks' extractions ({"chunk_id", "extraction"}) into entities and relations.

    Every entity and relation keeps the ids of the chunks it came from.
    """
    read = sorted(
        (x for x in extractions if x["extraction"] is not None), key=lambda x: x["chunk_id"]
    )
    occurrences = [(x["chunk_id"], e) for x in read for e in x["extraction"].entities]
    hub = _hub(occurrences)

    def clean(name: str) -> tuple[str, str, list[str]]:
        base, aliases = _split_nicknames(name)
        base = _strip_hub(base, hub)
        return normalize_name(base), base, aliases

    # Aliases point at their entity, unless two entities claim the same alias.
    claims: dict[str, set[str]] = {}
    for _, e in occurrences:
        key, _, aliases = clean(e.name)
        for alias in aliases:
            if normalize_name(alias) != key:
                claims.setdefault(normalize_name(alias), set()).add(key)
    alias_of = {alias: next(iter(keys)) for alias, keys in claims.items() if len(keys) == 1}

    def resolve(name: str) -> tuple[str, str, list[str]]:
        key, base, aliases = clean(name)
        if key in alias_of:
            return alias_of[key], base, aliases + [base]
        return key, base, aliases

    entities: dict[str, dict] = {}

    def add_entity(chunk_id, name, type_, description):
        key, base, aliases = resolve(name)
        slot = entities.setdefault(
            key,
            {"name": None, "first": base, "aliases": {}, "types": Counter(),
             "descriptions": [], "chunk_ids": set()},
        )
        if slot["name"] is None and normalize_name(base) == key:
            slot["name"] = base
        for alias in aliases:
            slot["aliases"].setdefault(normalize_name(alias), alias)
        slot["types"][type_] += 1
        slot["descriptions"].append(description)
        slot["chunk_ids"].add(chunk_id)

    for chunk_id, e in occurrences:
        add_entity(chunk_id, e.name, e.type, e.description)

    relations: dict[tuple[str, str], dict] = {}
    promoted: list[tuple[int, str, str]] = []
    for x in read:
        for r in x["extraction"].relations:
            ends = [resolve(r.source)[0], resolve(r.target)[0]]
            if ends[0] == ends[1]:
                continue  # both names were the same entity
            dangling = [(k, n) for k, n in zip(ends, (r.source, r.target)) if k not in entities]
            if any(re.search(r"\d", n) for _, n in dangling):
                continue  # a date, time or value: not an entity
            promoted.extend((x["chunk_id"], n, r.description) for _, n in dangling)
            slot = relations.setdefault(
                tuple(ends), {"keywords": [], "descriptions": [], "chunk_ids": set()}
            )
            slot["keywords"].append(r.keywords)
            slot["descriptions"].append(r.description)
            slot["chunk_ids"].add(x["chunk_id"])
    for chunk_id, name, description in promoted:
        add_entity(chunk_id, name, PROMOTED_TYPE, description)

    merged_entities = []
    for key, s in entities.items():
        name = s["name"] or s["first"]
        merged_entities.append(GraphEntity(
            key=key, name=name, type=s["types"].most_common(1)[0][0],
            description=_join(s["descriptions"]), chunk_ids=sorted(s["chunk_ids"]),
            aliases=[a for k, a in s["aliases"].items() if k != key],
        ))
    names = {e.key: e.name for e in merged_entities}
    merged_relations = [
        GraphRelation(
            source=names[source], target=names[target], source_key=source, target_key=target,
            keywords=_join(s["keywords"]), description=_join(s["descriptions"]),
            chunk_ids=sorted(s["chunk_ids"]),
        )
        for (source, target), s in relations.items()
    ]
    return merged_entities, merged_relations


def link_synonyms(entities: list[GraphEntity], embedder) -> list[GraphEntity]:
    """The entities, each with the keys (and cosine) of those whose names are close."""
    if len(entities) < 2:
        return entities
    vectors = np.array(embedder.embed_documents([e.name for e in entities]), dtype=float)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    unit = vectors / np.where(norms == 0, 1.0, norms)
    cosine = unit @ unit.T
    np.fill_diagonal(cosine, 0.0)
    return [
        e.model_copy(update={"synonyms": {
            entities[j].key: round(float(cosine[i, j]), 4)
            for j in np.flatnonzero(cosine[i] >= SYNONYM_COSINE)
        }})
        for i, e in enumerate(entities)
    ]
