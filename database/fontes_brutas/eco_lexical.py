"""Ação Q2 (plano da campanha 2, seção 7.2): eco lexical entre a pergunta e a evidência.

Eco = fração das palavras de conteúdo da pergunta que aparecem nos trechos de evidência
(mesma normalização de `overlap_metrics.normalize_pt_tokens`, sem palavras funcionais).
Com um arquivo de resultados, correlaciona o eco com o `context_all_hops` por pergunta
(Spearman), na Combinação indicada ou na média de todas as Combinações do arquivo.

    backend/.venv/bin/python database/fontes_brutas/eco_lexical.py <perguntas.csv> \\
        [<results.json> ...] [--combinacao chunking|embedding|retriever]
"""
import argparse
import csv
import json
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, "backend")
from app.core.evaluation.overlap_metrics import normalize_pt_tokens  # noqa: E402

_STOP = frozenset(
    "de do da dos das em no na nos nas por pelo pela pelos pelas para com sem e ou que qual quais "
    "quem quando onde como quanto quantos quantas se ao aos à às é são foi foram tem têm ter há "
    "mais menos seu sua seus suas este esta esse essa isso aquele aquela entre sobre até após "
    "já ainda também muito pouco".split()
)


def content(text: str) -> set[str]:
    return {t for t in normalize_pt_tokens(text) if t not in _STOP and len(t) > 1}


def echo(question: str, evidence: str) -> float:
    q = content(question)
    return len(q & content(evidence.replace("|", " "))) / len(q) if q else 0.0


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def _results(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        data = json.load(open(p, encoding="utf-8"))
        if isinstance(data, dict) and "results" in data:  # API dump of one Experimento
            data = data["results"]
        if isinstance(data, dict):  # campaign-1 export: {combination: {question: row}}
            data = [row for combo in data.values() for row in combo.values()]
        rows += data
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("perguntas")
    ap.add_argument("results", nargs="*")
    ap.add_argument("--combinacao", default=None)
    args = ap.parse_args()

    qs = list(csv.DictReader(open(args.perguntas, encoding="utf-8")))
    eco = {r["pergunta"]: echo(r["pergunta"], r["evidencia_referencia"]) for r in qs}
    tipo = {r["pergunta"]: r["tipo"] for r in qs}
    print(f"eco lexical: média {st.mean(eco.values()):.3f}, mediana {st.median(eco.values()):.3f}")
    by_type = defaultdict(list)
    for q, e in eco.items():
        by_type[tipo[q]].append(e)
    print("  por tipo:", {t: round(st.mean(v), 3) for t, v in by_type.items()})
    if not args.results:
        return

    hops = defaultdict(list)
    for r in _results(args.results):
        if r.get("rag", "naive") != "naive" or "context_all_hops" not in (r.get("scores") or {}):
            continue
        combo = f"{r['chunking']}|{r['embedding']}|{r['retriever']}"
        if args.combinacao and combo != args.combinacao:
            continue
        hops[r["question"]].append(r["scores"]["context_all_hops"])
    common = [q for q in eco if q in hops]
    a = [eco[q] for q in common]
    b = [st.mean(hops[q]) for q in common]
    label = args.combinacao or "média de todas as Combinações"
    print(f"Spearman(eco, all_hops) em {label}: rho = {spearman(a, b):.3f} (n = {len(common)})")


if __name__ == "__main__":
    main()
