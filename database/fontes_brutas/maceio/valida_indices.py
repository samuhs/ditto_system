"""B2.E0.2: every evidence passage of the question set must match a chunk of every Índice.

Reads the chunks straight from Qdrant (REST, port 6333) and reuses the matching rule of
backend/app/core/evaluation/gold_metrics.py. Run with the backend venv from the repo root:

    backend/.venv/bin/python database/fontes_brutas/maceio/valida_indices.py campanha-b2 database/perguntas_guia_maceio.csv
"""
import csv
import json
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, "backend")
from app.core.evaluation.gold_metrics import evidence_found_in  # noqa: E402

QDRANT = "http://localhost:6333"


def _get(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(QDRANT + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def chunks_of(collection: str) -> list[str]:
    texts, offset = [], None
    while True:
        body = {"limit": 256, "with_payload": ["text"], "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        page = _get(f"/collections/{collection}/points/scroll", body)["result"]
        texts += [p["payload"]["text"] for p in page["points"]]
        offset = page.get("next_page_offset")
        if offset is None:
            return texts


def main(base: str, questions: str) -> int:
    names = sorted(c["name"] for c in _get("/collections")["result"]["collections"]
                   if c["name"].startswith(base + "__") and "__kg_" not in c["name"])
    rows = list(csv.DictReader(open(questions, encoding="utf-8")))
    failures = 0
    for name in names:
        chunks = chunks_of(name)
        sizes = [len(c) for c in chunks]
        missing = []
        for row in rows:
            ev = row["evidencia_referencia"].split("|")
            hops = list(map(int, row["evidencia_salto"].split("|")))
            found = Counter()
            for passage, hop in zip(ev, hops):
                found[hop] += any(evidence_found_in(passage, c) for c in chunks)
            missing += [f"{row['pergunta'][:70]} (salto {h})" for h in set(hops) if not found[h]]
        failures += len(missing)
        print(f"{name}: {len(chunks)} chunks, média {sum(sizes) // len(sizes)} car., "
              f"máx {max(sizes)}; saltos sem evidência: {len(missing)}")
        for m in missing:
            print("   -", m)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
