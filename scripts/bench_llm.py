"""Benchmark an OpenAI-compatible LLM server under increasing concurrency.

Sends N RAG-shaped prompts (shared template + a context slice of the sample FAQ)
at each concurrency level and reports wall time, throughput and latency.
Stdlib only, so it runs on the host against Ollama, llama-server, mlx_lm.server, vLLM...

Usage: python3 scripts/bench_llm.py --model qwen2.5:3b-instruct [--base-url URL]
       [--levels 1,2,4,8] [-n 16] [--max-tokens 128]
"""
import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FAQ = Path(__file__).resolve().parents[1] / "database" / "faq_manus_completa.md"
TEMPLATE = (
    "Você é um assistente que responde perguntas usando apenas o contexto abaixo.\n"
    "Se a resposta não estiver no contexto, diga que não sabe.\n\n"
    "Contexto:\n{context}\n\nPergunta: {question}\nResposta:"
)
QUESTIONS = [
    "Quais são os principais pontos turísticos citados?",
    "Qual a melhor época para visitar?",
    "Como chegar à cidade?",
    "Quais opções de hospedagem existem?",
    "O que comer na região?",
    "Quais atividades ao ar livre são recomendadas?",
    "Há eventos ou festas tradicionais?",
    "Quais cuidados o viajante deve ter?",
]


def _prompts(n: int) -> list[str]:
    text = FAQ.read_text(encoding="utf-8") if FAQ.exists() else "Sem contexto disponível."
    size = 1500
    slices = [text[i : i + size] for i in range(0, max(len(text), 1), size)] or [text]
    return [
        TEMPLATE.format(context=slices[i % len(slices)], question=QUESTIONS[i % len(QUESTIONS)])
        for i in range(n)
    ]


def _call(base_url: str, model: str, prompt: str, max_tokens: int) -> tuple[float, int]:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer bench"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    elapsed = time.perf_counter() - start
    return elapsed, int((data.get("usage") or {}).get("completion_tokens") or 0)


def _p(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--levels", default="1,2,4,8")
    ap.add_argument("-n", type=int, default=16, help="requests per level")
    ap.add_argument("--max-tokens", type=int, default=128)
    args = ap.parse_args()

    prompts = _prompts(args.n)
    print(f"servidor {args.base_url} · modelo {args.model} · {args.n} requisições/nível · max_tokens {args.max_tokens}")
    _call(args.base_url, args.model, prompts[0], 8)  # warm-up: load the model

    header = f"{'paralelo':>8} {'tempo(s)':>9} {'req/s':>7} {'tok/s':>7} {'p50(s)':>7} {'p95(s)':>7}"
    print(header)
    print("-" * len(header))
    baseline = None
    for level in [int(x) for x in args.levels.split(",") if x.strip()]:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=level) as pool:
            results = list(pool.map(lambda p: _call(args.base_url, args.model, p, args.max_tokens), prompts))
        wall = time.perf_counter() - start
        latencies = [r[0] for r in results]
        tokens = sum(r[1] for r in results)
        baseline = baseline or wall
        print(
            f"{level:>8} {wall:>9.1f} {args.n / wall:>7.2f} {tokens / wall:>7.1f} "
            f"{statistics.median(latencies):>7.2f} {_p(latencies, 0.95):>7.2f}"
            f"   ({baseline / wall:.1f}x vs primeiro nível)"
        )


if __name__ == "__main__":
    main()
