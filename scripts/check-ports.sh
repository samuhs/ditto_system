#!/usr/bin/env bash
# Fails early, with the fix, when a port the stack publishes is taken by
# another program. Ports come from .env (WEB_PORT, API_PORT, POSTGRES_PORT,
# QDRANT_PORT) with the defaults below, the same ones docker-compose.yml uses.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh


# Ports the running Ditto stack already holds are fine.
ours=" $(docker compose ps --format '{{range .Publishers}}{{.PublishedPort}} {{end}}' 2>/dev/null | tr '\n' ' ') "

has lsof || { warn "lsof não disponível; pulei a checagem de portas"; exit 0; }

pairs="WEB_PORT:3000 API_PORT:8000 POSTGRES_PORT:5432 QDRANT_PORT:6333"
[ "$(llm_server)" = docker ] && pairs="$pairs OLLAMA_DOCKER_PORT:11435"

busy=0
for pair in $pairs; do
  var="${pair%%:*}"
  port="$(env_get "$var")"
  port="${port:-${pair##*:}}"
  case "$ours" in *" $port "*) continue ;; esac
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    proc="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1" (pid "$2")"}')"
    warn "porta $port em uso por ${proc:-outro processo}. Use outra: $var=$((port + 1)) no .env"
    busy=1
  fi
done
[ "$busy" = 0 ] || fail "portas ocupadas; ajuste o .env (ou pare o outro serviço) e rode de novo"
ok "portas livres"
