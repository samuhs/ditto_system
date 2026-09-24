#!/usr/bin/env bash
# Serves the LLM with Ollama inside Docker instead of on the host.
#
# Why: native Ollama talks to its own llama.cpp runner over a fixed
# 127.0.0.1 TCP port. Some corporate VPN/security agents on macOS break
# outgoing IPv4 loopback connections ("can't assign requested address"), so
# generation fails there no matter how OLLAMA_HOST is set. Inside the Docker
# VM that loopback is untouched. Trade-off: on macOS the container has no
# Metal GPU, so inference runs on the CPU.
#
# Writes LLM_SERVER, COMPOSE_PROFILES and OLLAMA_BASE_URL to .env, starts the
# ollama service, pulls MODEL and smoke-tests it from the api container.
# Env: MODEL, PARALLEL (default 2 here: CPU), YES=1.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

MODEL="${MODEL:-qwen2.5:3b-instruct}"
case "$MODEL" in *:*) ;; *) MODEL="$MODEL:latest" ;; esac
PARALLEL="${PARALLEL:-2}"

step "Ollama no Docker"
docker info >/dev/null 2>&1 || fail "o Docker não está respondendo. Abra o Docker Desktop e rode de novo."
if [ "$(uname -s)" = Darwin ]; then
  warn "no macOS o container não usa a GPU (Metal): a geração roda na CPU, mais devagar que o Ollama nativo"
fi
env_set LLM_SERVER docker
env_set COMPOSE_PROFILES ollama-docker
env_set OLLAMA_BASE_URL http://ollama:11434/v1
env_set OLLAMA_NUM_PARALLEL "$PARALLEL"
ok ".env: LLM_SERVER=docker, OLLAMA_BASE_URL=http://ollama:11434/v1, OLLAMA_NUM_PARALLEL=$PARALLEL"

docker compose up -d ollama >/dev/null 2>&1 \
  || fail "não consegui subir o container do Ollama (a imagem ollama/ollama foi baixada?). Veja: docker compose up ollama"
for _ in $(seq 1 30); do
  ollama_cli list >/dev/null 2>&1 && break
  sleep 1
done
ollama_cli list >/dev/null 2>&1 || fail "o Ollama do container não respondeu em 30s (docker compose logs ollama)"
ok "rodando no container 'ollama' (no host: http://localhost:$(env_get OLLAMA_DOCKER_PORT | grep . || echo 11435))"

step "Modelo $MODEL"
manifest_in() {
  # $1 = models dir; true when it already holds MODEL.
  local name="${MODEL%%:*}" tag="${MODEL#*:}"
  case "$name" in */*) ;; *) name="library/$name" ;; esac
  [ -f "$1/manifests/registry.ollama.ai/$name/$tag" ]
}
if ollama_cli list | awk 'NR>1{print $1}' | grep -Fxq "$MODEL"; then
  ok "já disponível"
else
  echo "  baixando dentro do container (pode levar alguns minutos)..."
  if ollama_cli pull "$MODEL"; then
    ok "baixado"
  elif manifest_in "$HOME/.ollama/models"; then
    # The container's egress is blocked but the host already has the model.
    warn "o container não conseguiu baixar; usando os modelos já baixados no host (~/.ollama/models)"
    env_set OLLAMA_MODELS_DIR "$HOME/.ollama/models"
    docker compose up -d ollama >/dev/null
    for _ in $(seq 1 30); do ollama_cli list >/dev/null 2>&1 && break; sleep 1; done
    ollama_cli list | awk 'NR>1{print $1}' | grep -Fxq "$MODEL" || fail "o modelo não apareceu no container"
    ok "modelo do host montado no container"
  else
    fail "o container não conseguiu baixar $MODEL. Se o host consegue, rode 'ollama pull $MODEL' no host e repita este comando: ele reaproveita ~/.ollama/models."
  fi
fi

step "Teste de geração"
start=$(date +%s)
reply="$(ollama_cli run "$MODEL" "Responda apenas: ok" 2>/dev/null | head -c 60)" || fail "a geração falhou (docker compose logs ollama)"
ok "resposta em $(( $(date +%s) - start ))s: $reply"

step "Conexão API → Ollama"
if [ -n "$(docker compose ps -q api 2>/dev/null)" ]; then
  # Recreate the api so it picks up the new OLLAMA_BASE_URL.
  docker compose up -d api >/dev/null 2>&1
  for _ in $(seq 1 20); do
    docker compose exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://ollama:11434/api/tags', timeout=5)" \
      >/dev/null 2>&1 && { ok "a API alcança o Ollama; o modelo aparece como '$MODEL' no app"; exit 0; }
    sleep 1
  done
  warn "a API ainda não alcança http://ollama:11434 (docker compose logs api)"
else
  ok "API ainda não está rodando; rode 'make up' (o Ollama do Docker sobe junto)"
fi
