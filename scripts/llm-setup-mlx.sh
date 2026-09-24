#!/usr/bin/env bash
# Serves the LLM with Apple MLX (mlx-lm) on the host: Metal GPU, the fastest
# local option on Apple Silicon. mlx_lm.server is a single process with an
# OpenAI-compatible API and batched decoding (PARALLEL requests at once).
#
# Installs mlx-lm into .tools/mlx, records the choice in .env, starts the
# server, downloads MODEL (a Hugging Face id; short names mean
# mlx-community/<name>) and smoke-tests it from the API container.
# Env: MODEL, PARALLEL (default 4), MLX_PORT (default 11436), YES=1.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

MODEL="$(mlx_model_id "${MODEL:-Qwen2.5-3B-Instruct-4bit}")"
PARALLEL="${PARALLEL:-4}"

step "MLX (Apple Silicon)"
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] \
  || fail "MLX só roda em Mac com Apple Silicon. Use: make llm-setup LLM_SERVER=host (ou docker)"
if ipv4_loopback_broken; then
  warn "o loopback IPv4 (127.0.0.1) está bloqueado nesta máquina (agente de VPN/segurança)"
  warn "a API no Docker não consegue falar com um servidor no host"
  if confirm "Usar o Ollama dentro do Docker (sem GPU, mas funciona com a VPN)?"; then
    exec ./scripts/llm-setup-docker.sh
  fi
  fail "sem o 127.0.0.1 o MLX não é alcançável; rode: make llm-setup LLM_SERVER=docker"
fi
ok "Metal GPU disponível"

./scripts/host-certs.sh >/dev/null

PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if has "$candidate" && "$candidate" -c 'import sys, platform; sys.exit(sys.version_info < (3, 11) or platform.machine() != "arm64")' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.11+ nativo (arm64) não encontrado. Instale o Python 3.13 (https://www.python.org/downloads/)."

[ -x "$MLX_PY" ] || "$PY" -m venv "$MLX_DIR"
pip_env=()
if [ -s certs/host-ca.pem ]; then
  bundle="$(mktemp)"
  cat "$("$MLX_PY" -c 'import pip._vendor.certifi as c; print(c.where())')" certs/host-ca.pem >"$bundle"
  pip_env=(PIP_CERT="$bundle")
fi
env ${pip_env[@]+"${pip_env[@]}"} "$MLX_PY" -m pip install --quiet --upgrade pip mlx-lm
ok "mlx-lm $("$MLX_PY" -c 'import importlib.metadata as m; print(m.version("mlx-lm"))') em $MLX_DIR"

step "Servidor MLX"
if [ "$(env_file_get LLM_SERVER)" != mlx ]; then
  reset_llm_server
fi
env_set LLM_SERVER mlx
env_set MLX_PARALLEL "$PARALLEL"
env_set OLLAMA_BASE_URL "http://host.docker.internal:$(mlx_port)/v1"
ok ".env: LLM_SERVER=mlx, OLLAMA_BASE_URL=http://host.docker.internal:$(mlx_port)/v1"
# Restart so a new PARALLEL takes effect.
./scripts/llm.sh down >/dev/null 2>&1 || true
./scripts/llm.sh up

step "Modelo $MODEL"
./scripts/model.sh add "$MODEL"

step "Teste de geração"
start=$(date +%s)
reply="$(curl -sf "$(mlx_url)/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Responda apenas: ok\"}],\"max_tokens\":10}" \
  | "$MLX_PY" -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])')" \
  || fail "a geração falhou (veja $MLX_DIR/server.log)"
ok "resposta em $(( $(date +%s) - start ))s (inclui carregar o modelo): $reply"

step "Conexão API → MLX"
if [ -n "$(docker compose ps -q api 2>/dev/null)" ]; then
  docker compose up -d api >/dev/null 2>&1   # pick up the new OLLAMA_BASE_URL
  for _ in $(seq 1 20); do
    docker compose exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://host.docker.internal:$(mlx_port)/v1/models', timeout=5)" \
      >/dev/null 2>&1 && { ok "a API alcança o MLX; o modelo aparece como '$MODEL' no app"; exit 0; }
    sleep 1
  done
  warn "a API não alcança o MLX em host.docker.internal:$(mlx_port) (docker compose logs api)"
else
  ok "API ainda não está rodando; rode 'make up' (ele também sobe o MLX)"
fi
