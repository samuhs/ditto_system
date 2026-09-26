#!/usr/bin/env python3
"""Collect open data about a Brazilian municipality into raw, auditable files.

Implements the "camada 1" (ready-made open data) of the city search plan with free, open sources only:
IBGE (localidades), Wikidata (SPARQL), Wikipedia and Wikivoyage (pt), the
OpenStreetMap Overpass API and the CNES open-data API (health facilities).

Every source is saved as fetched (JSON or plain text) plus a manifest with URL,
licence and retrieval time, so a knowledge base written from these files can
cite each fact. Standard library only: runs with any Python 3.10+.

    python3 <skill>/scripts/coletar_cidade.py "Santo Antônio da Alegria" SP
    python3 <skill>/scripts/coletar_cidade.py "Cajuru" SP --out /tmp/cajuru --only wikipedia osm
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "ditto-research/0.1 (PhD project; https://github.com/samuhs/ditto_system)"
TIMEOUT = 90
# Wikimedia and Overpass ask for gentle clients: one request at a time, with a pause.
PAUSE_SECONDS = 1.0

LICENSES = {
    "ibge": "Dado público (IBGE)",
    "wikidata": "CC0 (Wikidata)",
    "wikipedia": "CC BY-SA 4.0 (Wikipedia)",
    "wikivoyage": "CC BY-SA 4.0 (Wikivoyage)",
    "osm": "ODbL — © OpenStreetMap contributors",
    "cnes": "Dado público (CNES/DATASUS)",
}

# Keys whose presence makes an OSM element a point of interest worth listing.
OSM_POI_KEYS = "amenity|shop|tourism|leisure|historic|natural|office|healthcare|craft|public_transport|waterway"


def _slug(text: str) -> str:
    """Lowercase ASCII slug for directory names."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "_".join(ascii_text.lower().split())


def _get(url: str, params: dict | None = None, data: dict | None = None, accept: str = "application/json") -> bytes:
    """HTTP GET (or POST when data is given) with retries on 429/5xx."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    body = urllib.parse.urlencode(data).encode() if data else None
    for attempt in range(4):
        request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
            time.sleep(PAUSE_SECONDS)
            # Some servers (IBGE) gzip the body even when not asked to.
            return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            # Slow servers (IBGE, Overpass) time out now and then: retry like a 5xx.
            if attempt == 3:
                raise
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _json(url: str, **kwargs) -> dict | list:
    return json.loads(_get(url, **kwargs))


class Collector:
    """Fetches every source for one municipality and records a manifest."""

    def __init__(self, city: str, uf: str, out: Path) -> None:
        self.city, self.uf, self.out = city, uf.upper(), out
        self.out.mkdir(parents=True, exist_ok=True)
        self.manifest: list[dict] = []
        self.ibge_code: str | None = None

    def _save(self, name: str, source: str, url: str, content: dict | list | str) -> None:
        path = self.out / name
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        self.manifest.append({
            "arquivo": name,
            "fonte": source,
            "url": url,
            "licenca": LICENSES[source],
            "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        print(f"  ok  {name}", file=sys.stderr)

    # --- IBGE ---------------------------------------------------------------
    def ibge(self) -> None:
        """Municipality code and territorial hierarchy (the key for every other source)."""
        url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{self.uf}/municipios"
        target = _slug(self.city)
        matches = [m for m in _json(url) if _slug(m["nome"]) == target]
        if not matches:
            raise SystemExit(f"município não encontrado no IBGE: {self.city}/{self.uf}")
        municipio = matches[0]
        self.ibge_code = str(municipio["id"])
        self._save("ibge_municipio.json", "ibge", url, municipio)

    # --- Wikidata -----------------------------------------------------------
    def wikidata(self) -> None:
        """Structured facts keyed by the IBGE code (P1585)."""
        query = f"""
        SELECT ?item ?itemLabel ?populacao ?dataPop ?area ?altitude ?coord ?fundacao ?site
               (GROUP_CONCAT(DISTINCT ?vizinhoLabel; separator="|") AS ?vizinhos)
               (GROUP_CONCAT(DISTINCT ?padroeiroLabel; separator="|") AS ?padroeiros)
        WHERE {{
          ?item wdt:P1585 "{self.ibge_code}" .
          OPTIONAL {{ ?item p:P1082 ?st . ?st ps:P1082 ?populacao . OPTIONAL {{ ?st pq:P585 ?dataPop }} }}
          OPTIONAL {{ ?item wdt:P2046 ?area }}
          OPTIONAL {{ ?item wdt:P2044 ?altitude }}
          OPTIONAL {{ ?item wdt:P625 ?coord }}
          OPTIONAL {{ ?item wdt:P571 ?fundacao }}
          OPTIONAL {{ ?item wdt:P856 ?site }}
          OPTIONAL {{ ?item wdt:P47 ?vizinho . ?vizinho rdfs:label ?vizinhoLabel FILTER(lang(?vizinhoLabel)="pt") }}
          OPTIONAL {{ ?item wdt:P417 ?padroeiro . ?padroeiro rdfs:label ?padroeiroLabel FILTER(lang(?padroeiroLabel)="pt") }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en". }}
        }}
        GROUP BY ?item ?itemLabel ?populacao ?dataPop ?area ?altitude ?coord ?fundacao ?site
        """
        url = "https://query.wikidata.org/sparql"
        result = _json(url, params={"query": query, "format": "json"}, accept="application/sparql-results+json")
        rows = [{k: v["value"] for k, v in b.items()} for b in result["results"]["bindings"]]
        self._save("wikidata.json", "wikidata", url, rows)

    # --- Wikipedia / Wikivoyage ---------------------------------------------
    def _wiki_extract(self, host: str, source: str, name: str) -> None:
        url = f"https://{host}/w/api.php"
        params = {
            "action": "query", "prop": "extracts|info", "explaintext": 1, "inprop": "url",
            "titles": self.city, "redirects": 1, "format": "json",
        }
        pages = _json(url, params=params)["query"]["pages"]
        page = next(iter(pages.values()))
        if "missing" in page:
            print(f"  --  {source}: sem página para {self.city}", file=sys.stderr)
            return
        header = f"Fonte: {page['fullurl']}\nLicença: {LICENSES[source]}\n\n"
        self._save(name, source, page["fullurl"], header + page["extract"])

    def wikipedia(self) -> None:
        """Full plain-text article (history, geography, economy)."""
        self._wiki_extract("pt.wikipedia.org", "wikipedia", "wikipedia_pt.txt")

    def wikivoyage(self) -> None:
        """Travel guide article, when one exists (rare for small towns)."""
        self._wiki_extract("pt.wikivoyage.org", "wikivoyage", "wikivoyage_pt.txt")

    # --- OpenStreetMap ------------------------------------------------------
    def osm(self) -> None:
        """Named points of interest inside the municipal boundary."""
        query = (
            f'[out:json][timeout:120];area["IBGE:GEOCODIGO"="{self.ibge_code}"]->.a;'
            f'nwr(area.a)[name][~"^({OSM_POI_KEYS})$"~"."];out center tags;'
        )
        url = "https://overpass-api.de/api/interpreter"
        elements = _json(url, data={"data": query})["elements"]
        pois = [
            {
                "osm": f"{e['type']}/{e['id']}",
                "lat": e.get("lat", e.get("center", {}).get("lat")),
                "lon": e.get("lon", e.get("center", {}).get("lon")),
                "tags": e["tags"],
            }
            for e in elements
        ]
        self._save("osm_pois.json", "osm", url, pois)

    # --- CNES ---------------------------------------------------------------
    def cnes(self) -> None:
        """Health facilities (hospitals, UBS, clinics, pharmacies registered in CNES)."""
        url = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
        code6 = self.ibge_code[:6]  # CNES uses the 6-digit IBGE code (no check digit)
        rows: list[dict] = []
        offset = 0
        while True:
            page = _json(url, params={"codigo_municipio": code6, "limit": 20, "offset": offset})
            batch = page.get("estabelecimentos", [])
            rows.extend(batch)
            if len(batch) < 20:
                break
            offset += 20
        self._save("cnes_estabelecimentos.json", "cnes", f"{url}?codigo_municipio={code6}", rows)

    def run(self, only: list[str]) -> None:
        steps = ["ibge", "wikidata", "wikipedia", "wikivoyage", "osm", "cnes"]
        self.ibge()  # always: every other step needs the code
        for step in steps[1:]:
            if only and step not in only:
                continue
            try:
                getattr(self, step)()
            except Exception as exc:  # keep errors visible, never silent (visible errors)
                print(f"  ERRO {step}: {exc}", file=sys.stderr)
                self.manifest.append({"fonte": step, "erro": str(exc)})
        (self.out / "manifesto.json").write_text(
            json.dumps({"cidade": self.city, "uf": self.uf, "ibge": self.ibge_code, "arquivos": self.manifest},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cidade")
    parser.add_argument("uf")
    parser.add_argument("--out", type=Path, help="pasta de saída (padrão: database/fontes_brutas/<cidade>)")
    parser.add_argument("--only", nargs="*", default=[], help="wikidata wikipedia wikivoyage osm cnes")
    args = parser.parse_args()
    # Default: <cwd>/database/fontes_brutas/<cidade> in a project with a database/ folder, else <cwd>/fontes_brutas/<cidade>.
    root = Path.cwd() / "database" if (Path.cwd() / "database").is_dir() else Path.cwd()
    out = args.out or root / "fontes_brutas" / _slug(args.cidade)
    print(f"coletando {args.cidade}/{args.uf} em {out}", file=sys.stderr)
    Collector(args.cidade, args.uf, out).run(args.only)


if __name__ == "__main__":
    main()
