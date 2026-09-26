"""Perplexity of each question under an MLX model: one forward pass per question.

Runs with the MLX virtualenv's Python (~/.ditto/mlx/bin/python), outside the
MLX server, which cannot score a prompt's own tokens. The API calls it once
per model after an experiment's answers are generated.

stdin:  {"model": "<hf id>", "questions": ["...", ...]}
stdout: {"perplexity": {"<question>": <float>, ...}}

Each question is scored after a fixed prefix, so its first token is scored in
context: perplexity = exp(mean negative log-likelihood of the question tokens).
"""
import json
import math
import sys

import mlx.core as mx
from mlx_lm import load

PREFIX = "Pergunta: "


def question_perplexity(model, tokenizer, question: str) -> float:
    prefix = tokenizer.encode(PREFIX)
    tokens = tokenizer.encode(PREFIX + question)
    start = len(prefix)
    if len(tokens) <= start:
        return float("nan")
    logits = model(mx.array(tokens)[None])[0].astype(mx.float32)
    logprobs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
    targets = mx.array(tokens[start:])
    # Token i is predicted by the logits at position i - 1.
    picked = mx.take_along_axis(logprobs[start - 1 : -1], targets[:, None], axis=-1)
    return math.exp(-picked.mean().item())


def main() -> None:
    request = json.load(sys.stdin)
    model, tokenizer = load(request["model"])
    scores = {q: question_perplexity(model, tokenizer, q) for q in request["questions"]}
    json.dump({"perplexity": scores}, sys.stdout)


if __name__ == "__main__":
    main()
