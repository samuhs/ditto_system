#!/usr/bin/env python3
"""Download web pages as Markdown for a knowledge base, keeping source and date.

Two modes. `jina` (default) uses the free Jina Reader (https://r.jina.ai/<url>),
which renders JavaScript and returns Markdown ready for an LLM, but allows only ~20 requests/minute. `direto` downloads the HTML and
keeps the text of the main content, with the standard library only: much
faster, and enough for server-rendered sites (most prefeituras). Each page becomes
<out>/<slug>.md with a header (URL, retrieval time) and is listed in
<out>/paginas.json, so every fact in a base built from it can be traced back.

Respect robots.txt and the site's terms. Never scrape Google Maps, TripAdvisor
or other sources whose terms forbid storing their data (see SKILL.md, collection rules).

    python3 <skill>/scripts/baixar_paginas.py database/fontes_brutas/santo_antonio_da_alegria/web URL [URL ...]
    python3 <skill>/scripts/baixar_paginas.py OUT --from-file urls.txt --modo direto
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "ditto-research/0.1 (PhD project; https://github.com/samuhs/ditto_system)"
READER = "https://r.jina.ai/"
# Without an API key Jina allows ~20 requests/minute.
PAUSE_SECONDS = 3.5


def _slug(url: str) -> str:
    """Filesystem-safe name from the URL host and path."""
    text = re.sub(r"^https?://(www\.)?", "", url).strip("/")
    return re.sub(r"[^A-Za-z0-9]+", "_", text)[:120].strip("_")


def fetch(url: str) -> str:
    """The page as Markdown, via Jina Reader."""
    request = urllib.request.Request(READER + url, headers={"User-Agent": USER_AGENT, "X-Return-Format": "markdown"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


_DROP_BLOCKS = re.compile(r"(?is)<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>")
_BREAKS = re.compile(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr|section|article)>")
_HEADINGS = re.compile(r"(?i)<h([1-6])[^>]*>")
_TAGS = re.compile(r"<[^>]+>")


def html_to_text(page: str, min_chars: int = 30) -> str:
    """Readable text of an HTML page: drops scripts, menus and short link lines.

    A crude stand-in for Trafilatura (Trafilatura-like extraction) that needs no
    install. Headings are kept as Markdown so the page structure survives.
    """
    page = _DROP_BLOCKS.sub("", page)
    page = _HEADINGS.sub(lambda m: "\n" + "#" * int(m.group(1)) + " ", page)
    page = _BREAKS.sub("\n", page)
    text = html.unescape(_TAGS.sub("", page))
    lines, seen = [], set()
    for line in (" ".join(l.split()) for l in text.splitlines()):
        # Keep headings, real sentences and short factual lines (addresses, phones,
        # e-mails, hours all carry a digit or "@"); drop menu items and repeated boilerplate.
        factual = any(ch.isdigit() for ch in line) or "@" in line
        if (line.startswith("#") or len(line) >= min_chars or factual) and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def fetch_direct(url: str) -> str:
    """The page's main text, from its raw HTML."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return html_to_text(response.read().decode(charset, errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--from-file", type=Path, help="um URL por linha (# comenta)")
    parser.add_argument("--modo", choices=["jina", "direto"], default="jina")
    parser.add_argument("--pausa", type=float, help="segundos entre páginas (padrão: 3.5 jina, 1 direto)")
    parser.add_argument("--paralelo", type=int, default=1, help="conexões simultâneas (padrão 1; no máximo 3 em sites pequenos)")
    parser.add_argument("--pular-existentes", action="store_true", help="não baixa de novo URLs já listados em paginas.json")
    args = parser.parse_args()
    urls = list(args.urls)
    if args.from_file:
        urls += [l.strip() for l in args.from_file.read_text().splitlines() if l.strip() and not l.startswith("#")]
    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "paginas.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    fetcher = fetch if args.modo == "jina" else fetch_direct
    pause = args.pausa if args.pausa is not None else (PAUSE_SECONDS if args.modo == "jina" else 1.0)
    if args.pular_existentes:
        done = {e["url"] for e in index if "arquivo" in e and (args.out / e["arquivo"]).exists()}
        urls = [u for u in urls if u not in done]

    def download(url: str) -> dict:
        name = f"{_slug(url)}.md"
        try:
            text = fetcher(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  ERRO {url}: {exc}", file=sys.stderr)
            return {"url": url, "erro": str(exc)}
        retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (args.out / name).write_text(f"<!-- fonte: {url} | coletado_em: {retrieved} -->\n{text}", encoding="utf-8")
        print(f"  ok  {name} ({len(text)} chars)", file=sys.stderr)
        time.sleep(pause)
        return {"url": url, "arquivo": name, "coletado_em": retrieved, "modo": args.modo, "caracteres": len(text)}

    # A few parallel connections at most: small sites (prefeituras) are slow and fragile.
    with ThreadPoolExecutor(max_workers=args.paralelo) as pool:
        results = list(pool.map(download, urls))
    fetched = {r["url"] for r in results}
    index = [e for e in index if e.get("url") not in fetched] + results
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
