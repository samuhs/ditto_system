#!/usr/bin/env python3
"""Compile an annotated knowledge-base master into an ingestible base plus sources.

The master is Markdown where each unit (a `###` block) carries one HTML comment
with its annotations, right below the heading:

    ### Bar do Hélio: bar e restaurante em Santo Antônio da Alegria
    <!-- fontes: pref:turismo/bar-do-helio, osm:way/452300226 | confianca: oficial | nota: texto livre -->
    O Bar do Hélio fica na Rodovia Altino Arantes, km 1,5...

Output:
- the clean base (comments removed), ready for /ingest;
- a JSON sidecar with, per block: section, heading, sources (URL, licence,
  retrieval date), confidence and notes; plus the document-level lists
  `conflitos` and `lacunas` taken from `<!-- conflito: ... -->` and
  `<!-- lacuna: ... -->` comments anywhere in the master;
- a check of database/DIRETRIZES.md rules (block size, blank lines inside a
  block, citation markers, relative dates, missing annotation). Exit code 1 on
  any violation.

Source aliases (extend SOURCES for other cities or sites):

    pref:<path>    site da Prefeitura (base URL passed with --prefeitura)
    wiki           Wikipedia (pt) article, from the manifest
    wikidata       Wikidata item, from the manifest
    ibge           IBGE localidades
    osm:<type/id>  OpenStreetMap element
    cnes:<code>    CNES health facility
    web:<url>      any other page (use for secondary sources)
    manus          database/faq_manus_completa.md (LLM-generated, unverified)

    python3 tools/buscador/compilar_base.py MASTER.md --saida BASE.md \\
        --brutos database/fontes_brutas/<cidade> --prefeitura https://<site>/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

MAX_BLOCK_CHARS = 800
_COMMENT = re.compile(r"<!--\s*(.*?)\s*-->", re.S)
_CITATION = re.compile(r"\[\d+(,\s*\d+)*\]")
_RELATIVE_TIME = re.compile(r"\b(hoje|nesta semana|essa semana|esta semana|atualmente|data atual|este ano|ano passado)\b", re.I)

LICENCES = {
    "pref": "Dado público (site da Prefeitura)",
    "wiki": "CC BY-SA 4.0 (Wikipedia)",
    "wikidata": "CC0 (Wikidata)",
    "ibge": "Dado público (IBGE)",
    "osm": "ODbL — © OpenStreetMap contributors",
    "cnes": "Dado público (CNES/DATASUS)",
    "web": "Página da web (verificar termos de uso)",
    "manus": "Texto gerado por LLM (Manus), sem fontes verificáveis",
}


class Resolver:
    """Turns source aliases into URLs and retrieval dates from the raw-data folder."""

    def __init__(self, brutos: Path | None, prefeitura: str | None) -> None:
        self.prefeitura = (prefeitura or "").rstrip("/") + "/"
        self.dates: dict[str, str] = {}
        self.manifest: dict[str, str] = {}
        if brutos:
            manifest = brutos / "manifesto.json"
            if manifest.exists():
                for entry in json.loads(manifest.read_text()).get("arquivos", []):
                    if "url" in entry:
                        self.manifest[entry["fonte"]] = entry["url"]
                        self.dates[entry["url"]] = entry["coletado_em"]
            for index in brutos.rglob("paginas.json"):
                for entry in json.loads(index.read_text()):
                    if "coletado_em" in entry:
                        self.dates[entry["url"]] = entry["coletado_em"]

    def resolve(self, alias: str) -> dict:
        kind, _, rest = alias.partition(":")
        if kind not in LICENCES:
            raise ValueError(f"fonte desconhecida: {alias}")
        url = {
            "pref": self.prefeitura + rest,
            "wiki": self.manifest.get("wikipedia", ""),
            "wikidata": self.manifest.get("wikidata", ""),
            "ibge": self.manifest.get("ibge", ""),
            "osm": f"https://www.openstreetmap.org/{rest}",
            "cnes": f"https://cnes.datasus.gov.br/pages/estabelecimentos/consulta.jsp?search={rest}",
            "web": rest,
            "manus": "database/faq_manus_completa.md",
        }[kind]
        if kind == "cnes":
            collected = self.dates.get(self.manifest.get("cnes", ""), "")
        elif kind == "osm":
            collected = self.dates.get(self.manifest.get("osm", ""), "")
        else:
            collected = self.dates.get(url, "")
        return {"fonte": alias, "url": url, "licenca": LICENCES[kind], "coletado_em": collected}


def _fields(comment: str) -> dict[str, str]:
    """'fontes: a, b | confianca: x | nota: y' -> dict."""
    out = {}
    for part in comment.split("|"):
        key, _, value = part.partition(":")
        out[key.strip().lower()] = value.strip()
    return out


def compile_master(text: str, resolver: Resolver) -> tuple[str, dict, list[str]]:
    """Clean base text, sidecar dict and a list of guideline violations."""
    conflicts, gaps = [], []
    for comment in _COMMENT.findall(text):
        key, _, value = comment.partition(":")
        if key.strip() == "conflito":
            conflicts.append(value.strip())
        elif key.strip() == "lacuna":
            gaps.append(value.strip())

    blocks, problems = [], []
    section = ""
    out_chunks: list[str] = []
    for raw_block in re.split(r"\n\s*\n", text.strip()):
        # Document-level comments (conflito/lacuna) never reach the base.
        cleaned = _COMMENT.sub("", raw_block).strip()
        cleaned = "\n".join(line for line in cleaned.splitlines() if line.strip())
        if not cleaned:
            continue
        first = cleaned.splitlines()[0]
        if first.startswith("## "):
            section = first[3:].strip()
        if first.startswith("### "):
            heading = first[4:].strip()
            notes = [c for c in _COMMENT.findall(raw_block) if c.lstrip().startswith("fontes")]
            if not notes:
                problems.append(f"sem anotação de fontes: {heading}")
                meta = {}
            else:
                meta = _fields(notes[0])
            sources = [resolver.resolve(a.strip()) for a in meta.get("fontes", "").split(",") if a.strip()]
            blocks.append({
                "secao": section,
                "cabecalho": heading,
                "fontes": sources,
                "confianca": meta.get("confianca", ""),
                "nota": meta.get("nota", ""),
                "caracteres": len(cleaned),
            })
            if len(cleaned) > MAX_BLOCK_CHARS:
                problems.append(f"bloco com {len(cleaned)} caracteres (> {MAX_BLOCK_CHARS}): {heading}")
        if _CITATION.search(cleaned):
            problems.append(f"marcador de citação: {first}")
        if match := _RELATIVE_TIME.search(cleaned):
            problems.append(f"tempo relativo ('{match.group(0)}'): {first}")
        out_chunks.append(cleaned)

    sidecar = {
        "gerado_em": date.today().isoformat(),
        "blocos": blocks,
        "conflitos": conflicts,
        "lacunas": gaps,
    }
    return "\n\n".join(out_chunks) + "\n", sidecar, problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("master", type=Path)
    parser.add_argument("--saida", type=Path, required=True, help="base limpa (.md)")
    parser.add_argument("--fontes", type=Path, help="JSON de anotações (padrão: <saida>.fontes.json)")
    parser.add_argument("--brutos", type=Path, help="pasta de fontes_brutas da cidade (datas de coleta)")
    parser.add_argument("--prefeitura", help="URL base do site da Prefeitura, para o alias pref:")
    args = parser.parse_args()
    base, sidecar, problems = compile_master(args.master.read_text(encoding="utf-8"), Resolver(args.brutos, args.prefeitura))
    sidecar["documento"] = str(args.saida)
    sidecar["mestre"] = str(args.master)
    args.saida.write_text(base, encoding="utf-8")
    fontes = args.fontes or args.saida.with_suffix(".fontes.json")
    fontes.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(sidecar['blocos'])} blocos, {len(sidecar['conflitos'])} conflitos, {len(sidecar['lacunas'])} lacunas "
          f"-> {args.saida}, {fontes}", file=sys.stderr)
    for problem in problems:
        print(f"  VIOLAÇÃO {problem}", file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
