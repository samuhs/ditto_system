"""Regra R1 (plano da campanha 2, seção 7.1): marca as perguntas que o LLM responde sem contexto.

Para cada resposta `closed_book`, conta quantos fatos-chave da pergunta aparecem na resposta:
- fato com dígitos: todos os números do fato precisam aparecer como números na resposta
  (separador de milhar e "º" ignorados; "1.100 m" casa com "1100 metros");
- fato só com texto: `rapidfuzz.partial_ratio >= 85` depois de normalizar caixa e acentos.

Classe por pergunta: "vazamento" (todos os fatos), "parcial" (pelo menos metade), "nao".
É uma triagem: toda pergunta marcada é lida à mão (R1). Em `comparacao` o script não confere
qual lado a resposta escolhe, e um chute certo ou de senso comum também é marcado.
Uso, a partir da raiz do repositório:

    backend/.venv/bin/python database/fontes_brutas/vazamento_fatos_chave.py \\
        <fatos_chave.csv> <results.json> [--llm <nome>] [--detalhe]
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict

from rapidfuzz import fuzz

TEXT_THRESHOLD = 85


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def _numbers(text: str) -> set[str]:
    text = text.replace("º", "").replace("ª", "")
    text = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text)  # 6.775 -> 6775
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+(?:,\d+)?", text)}


# A number followed by a unit only counts when the answer has it with the same unit, so
# "30 minutos" does not match "30 km" and "1 hora e 30" does not match "30 km".
_UNITS = {
    "m": r"(?:m\b|metros?\b)", "km": r"(?:km\b|quil[oô]metros?\b)", "h": r"(?:h\b|:\d\d)",
    "m²": r"(?:m²|m2\b|metros quadrados)", "pessoas": r"pessoas", "habitantes": r"habitantes",
}


def _with_unit(number: str, unit: str, answer: str) -> bool:
    pattern = _UNITS.get(unit, re.escape(unit[:4]))
    num = re.escape(number)
    plain = _plain(answer).replace("º", "")
    plain = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", plain)
    return re.search(rf"(?<![\d,])0?{num}\s*{_plain(pattern) if unit not in _UNITS else pattern}", plain) is not None


def fact_found(fact: str, answer: str) -> bool:
    pairs = re.findall(r"(\d[\d.,]*)\s*(m²|km|m|h|pessoas|habitantes)\b", fact.replace("º", ""))
    if pairs:
        return all(_with_unit(re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", n), u, answer) for n, u in pairs)
    if re.search(r"\d", fact):
        return _numbers(fact) <= _numbers(answer)
    return fuzz.partial_ratio(_plain(fact), _plain(answer)) >= TEXT_THRESHOLD


def classify(facts: list[str], answer: str) -> tuple[str, int]:
    hits = sum(fact_found(f, answer) for f in facts)
    if hits == len(facts):
        return "vazamento", hits
    return ("parcial" if hits * 2 >= len(facts) else "nao"), hits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fatos")
    ap.add_argument("results")
    ap.add_argument("--llm", default=None, help="filtra um LLM (padrão: todos, um bloco por LLM)")
    ap.add_argument("--detalhe", action="store_true")
    args = ap.parse_args()

    facts = {r["pergunta"]: (r["tipo"], r["fatos_chave"].split("|"))
             for r in csv.DictReader(open(args.fatos, encoding="utf-8"))}
    rows = [r for r in json.load(open(args.results, encoding="utf-8")) if r["rag"] == "closed_book"]
    if args.llm:
        rows = [r for r in rows if r["llm"] == args.llm]
    by_llm = defaultdict(dict)
    for r in rows:
        if r["question"] in facts:
            by_llm[r["llm"]][r["question"]] = r["answer"]  # one closed_book answer per (llm, question)

    for llm, answers in sorted(by_llm.items()):
        total, per_type = Counter(), defaultdict(Counter)
        print(f"\n== {llm} ({len(answers)} perguntas)")
        for q, (tipo, fs) in facts.items():
            if q not in answers:
                continue
            cls, hits = classify(fs, answers[q])
            total[cls] += 1
            per_type[tipo][cls] += 1
            if args.detalhe and cls != "nao":
                print(f"  [{cls}] {hits}/{len(fs)} {q[:70]}\n      resposta: {answers[q][:160]!r}")
        n = sum(total.values())
        print(f"  vazamento {total['vazamento']}/{n} · parcial {total['parcial']}/{n} · nao {total['nao']}/{n}")
        for tipo, c in per_type.items():
            print(f"    {tipo}: vazamento {c['vazamento']}, parcial {c['parcial']}, nao {c['nao']}")


if __name__ == "__main__":
    main()
