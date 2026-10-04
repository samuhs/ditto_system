"""Quality gate for the knowledge-graph extractor: precision/recall against a hand-made key.

Runs the graph extraction prompt (the one saved under Prompts) on each section of
the key with an LLM extractor, then compares what it found with the annotated
entities and relations. Names match after lowercasing and dropping accents, with
fuzzy matching (ratio) that tolerates small spelling slips; name variants such
as "Cachoeira do Dédi" are listed as aliases in the key. Relations have no direction.

Usage (from the repo root, with the backend venv), or make graph-gate MODEL=...:
  backend/.venv/bin/python scripts/graph_extraction_gate.py \
      --model mlx-community/Qwen2.5-7B-Instruct-4bit [--gold PATH] [--base-url URL]
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rapidfuzz import fuzz  # noqa: E402

from app.core.graph.extraction import extract, without_headings  # noqa: E402
from app.core.llm.factory import is_local_llm, resolve_llm  # noqa: E402

DEFAULT_GOLD = ROOT / "database" / "guia_santo_antonio_da_alegria.grafo_gabarito.json"
DEFAULT_BASE = ROOT / "database" / "guia_santo_antonio_da_alegria.md"
MATCH_THRESHOLD = 90
GATE_ENTITY_RECALL = 0.6


def _normalize(name: str) -> str:
    """Lowercase, without accents or a parenthesised alias.

    "Cachoeira do Deosdédi (Cachoeira do Dédi)" -> "cachoeira do deosdedi".
    """
    name = re.sub(r"\s*\([^)]*\)", "", name)
    folded = unicodedata.normalize("NFKD", name.casefold())
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def _section(base_text: str, heading: str) -> str:
    """The section's text, heading included, up to the next blank line (the gate drops the heading as the build does)."""
    start = base_text.index(heading)
    end = base_text.find("\n\n", start)
    return base_text[start:end if end != -1 else None].strip()


def _match(name: str, gold: list[dict]) -> int | None:
    """Index of the gold entity this name refers to, or None."""
    target = _normalize(name)
    best, best_score = None, 0.0
    for i, entity in enumerate(gold):
        for candidate in [entity["nome"], *entity.get("aliases", [])]:
            score = fuzz.ratio(target, _normalize(candidate))
            if score > best_score:
                best, best_score = i, score
    return best if best_score >= MATCH_THRESHOLD else None


def _score_section(section: dict, extraction) -> dict:
    """Counts behind precision and recall of one section's entities and relations."""
    gold = section["entidades"]
    by_name = {_normalize(e["nome"]): i for i, e in enumerate(gold)}
    gold_pairs = {
        frozenset((by_name[_normalize(a)], by_name[_normalize(b)])) for a, b in section["relacoes"]
    }
    entity_matches = [_match(e.name, gold) for e in extraction.entities]
    relation_pairs = [
        frozenset((_match(r.source, gold), _match(r.target, gold))) for r in extraction.relations
    ]
    return {
        "entities_gold": len(gold),
        "entities_found": len(set(entity_matches) - {None}),
        "entities_predicted": len(entity_matches),
        "entities_correct": sum(m is not None for m in entity_matches),
        "relations_gold": len(gold_pairs),
        "relations_found": len(gold_pairs & set(relation_pairs)),
        "relations_predicted": len(relation_pairs),
        "relations_correct": sum(pair in gold_pairs for pair in relation_pairs),
        "failed_lines": extraction.failed_lines,
    }


def _ratio(a: int, b: int) -> float:
    """a / b, or 0 when there is nothing to divide by."""
    return a / b if b else 0.0


def _section_label(title: str) -> str:
    """The section heading without its '### ' marker, cut to fit the table."""
    return title.removeprefix("### ")[:44]


def main() -> int:
    """Run the extractor on every section of the gold key and print the scores."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True, help="local LLM extractor (MLX or Ollama name)")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD, help="gold key (JSON)")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument(
        "--base-url", default=None, help="local LLM server (default: OLLAMA_BASE_URL)"
    )
    args = parser.parse_args()
    if not is_local_llm(args.model):
        parser.error(f"{args.model} is not a local model: the gate runs only on MLX/Ollama")

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    base_text = args.base.read_text(encoding="utf-8")
    server = {"base_url": args.base_url} if args.base_url else {}
    llm = resolve_llm(args.model, temperature=0, **server)

    totals: dict[str, int] = {}
    print(f"LLM extrator: {args.model}\n")
    columns = ("ent R", "ent P", "rel R", "rel P", "falhas", "s")
    print(f"{'seção':<44} " + " ".join(f"{c:>6}" for c in columns))
    for section in gold["secoes"]:
        start = time.perf_counter()
        extraction = extract(llm, without_headings(_section(base_text, section["titulo"])))
        seconds = time.perf_counter() - start
        score = _score_section(section, extraction)
        for name, count in score.items():
            totals[name] = totals.get(name, 0) + count
        print(
            f"{_section_label(section['titulo']):<44} "
            f"{_ratio(score['entities_found'], score['entities_gold']):6.2f} "
            f"{_ratio(score['entities_correct'], score['entities_predicted']):6.2f} "
            f"{_ratio(score['relations_found'], score['relations_gold']):6.2f} "
            f"{_ratio(score['relations_correct'], score['relations_predicted']):6.2f} "
            f"{score['failed_lines']:6d} {seconds:5.1f}"
        )

    entity_recall = _ratio(totals["entities_found"], totals["entities_gold"])
    entity_precision = _ratio(totals["entities_correct"], totals["entities_predicted"])
    relation_recall = _ratio(totals["relations_found"], totals["relations_gold"])
    relation_precision = _ratio(totals["relations_correct"], totals["relations_predicted"])
    print(
        f"\nentidades: recall {entity_recall:.2f}, precisão {entity_precision:.2f}\n"
        f"relações:  recall {relation_recall:.2f}, precisão {relation_precision:.2f}\n"
        f"linhas com falha de formato: {totals['failed_lines']}"
    )
    if not gold.get("revisado"):
        print("\natenção: o gabarito ainda não foi revisado por uma pessoa")
    passed = entity_recall >= GATE_ENTITY_RECALL
    verdict = "passou" if passed else "NÃO passou"
    print(f"\nportão (recall de entidades ≥ {GATE_ENTITY_RECALL:.0%}): {verdict}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
