#!/usr/bin/env bash
# Runs Ditto with the API and the frontend on the host (no Docker for them):
# only Postgres and Qdrant stay in containers. Every local hop goes over IPv6
# loopback ([::1]), which keeps working on machines where a VPN/security agent
# breaks IPv4 loopback connections (errno 49), and needs no API container to
# reach a host LLM server.
#
#   local.sh up      make up-local
#   local.sh down    make down-local
#   local.sh status
#
# The Docker flow (make up) is untouched; running one stops the other's
# api/frontend so they never fight over the ports.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

RUN_DIR=".tools/local"
API_PID="$RUN_DIR/api.pid"
WEB_PID="$RUN_DIR/web.pid"
mkdir -p "$RUN_DIR"

port() { local v; v="$(env_get "$1")"; echo "${v:-$2}"; }
API_PORT="$(port API_PORT 8000)"
WEB_PORT="$(port WEB_PORT 3000)"
PG_PORT="$(port POSTGRES_PORT 5432)"
QD_PORT="$(port QDRANT_PORT 6333)"

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
wait_http() {
  # $1 url, $2 seconds, $3 pid file of the process to watch
  for _ in $(seq 1 "$2"); do
    curl -sf -o /dev/null "$1" && return 0
    [ -n "${3:-}" ] && ! alive "$3" && return 1
    sleep 1
  done
  return 1
}
stop_pid() {
  alive "$1" || { rm -f "$1"; return 1; }
  local pid; pid="$(cat "$1")"
  pkill -P "$pid" 2>/dev/null   # children (npm -> vite, uvicorn reloader)
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -9 "$pid" 2>/dev/null
  rm -f "$1"
}

# The LLM server's URL as the host API sees it, over IPv6 where possible.
llm_url_local() {
  case "$(llm_server)" in
    mlx) echo "http://[::1]:$(mlx_port)/v1" ;;
    docker) echo "http://[::1]:$(port OLLAMA_DOCKER_PORT 11435)/v1" ;;
    host) echo "http://localhost:11434/v1" ;;
  esac
}

up() {
  ./scripts/memory-profile.sh init
  step "Pré-requisitos"
  [ -x backend/.venv/bin/uvicorn ] || fail "backend/.venv não existe. Rode: make setup-dev"
  [ -d frontend/node_modules ] || fail "frontend/node_modules não existe. Rode: make setup-dev"
  docker info >/dev/null 2>&1 || fail "o Docker não está respondendo (ele ainda roda o Postgres e o Qdrant). Abra o Docker Desktop."
  ok "venv, dependências do frontend e Docker prontos"
  icloud_warning
  ipv4_loopback_broken && warn "loopback IPv4 bloqueado nesta máquina: tudo vai por IPv6 ([::1])"
  backend/.venv/bin/python -c 'import sentence_transformers' >/dev/null 2>&1 \
    || warn "embedders locais (e5, paraphrase) indisponíveis fora do Docker; para usá-los: LOCAL=1 make setup-dev"

  # Host Python trusts only certifi; add the host CAs (VPN/proxy that inspects
  # HTTPS) so Gemini and Hugging Face calls from the API keep verifying TLS.
  ./scripts/host-certs.sh >/dev/null
  CA_ENV=()
  if [ -s certs/host-ca.pem ]; then
    cat "$(backend/.venv/bin/python -c 'import certifi; print(certifi.where())')" certs/host-ca.pem \
      >"$RUN_DIR/ca-bundle.pem" 2>/dev/null \
      && CA_ENV=(SSL_CERT_FILE="$PWD/$RUN_DIR/ca-bundle.pem" REQUESTS_CA_BUNDLE="$PWD/$RUN_DIR/ca-bundle.pem")
  fi

  step "Postgres e Qdrant (Docker)"
  # The Docker api/frontend would hold the same ports.
  if [ -n "$(docker compose ps -q api frontend 2>/dev/null)" ]; then
    docker compose stop api frontend >/dev/null 2>&1
    ok "api e frontend do Docker parados (o modo local usa as mesmas portas)"
  fi
  services="postgres qdrant"
  [ "$(llm_server)" = docker ] && services="$services ollama"
  # shellcheck disable=SC2086
  docker compose up -d $services >/dev/null 2>&1 || fail "não consegui subir $services (docker compose up $services)"
  for _ in $(seq 1 30); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null)" = healthy ] && break
    sleep 1
  done
  ok "Postgres em [::1]:$PG_PORT, Qdrant em [::1]:$QD_PORT"

  step "Servidor de LLM ($(llm_server))"
  if [ "$(llm_server)" = mlx ]; then
    MLX_HOST=::1 ./scripts/llm.sh up || warn "MLX não subiu; o app funciona só com o Gemini até resolver (make llm-setup)"
  else
    ./scripts/llm.sh up || warn "servidor de LLM indisponível; o app funciona só com o Gemini até resolver"
  fi
  LLM_URL="$(llm_url_local)"

  step "API (host, IPv6)"
  if alive "$API_PID"; then
    ok "já rodando (pid $(cat "$API_PID"))"
  else
    for p in "$API_PORT" "$WEB_PORT"; do
      if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
        fail "porta $p ocupada por $(lsof -nP -iTCP:"$p" -sTCP:LISTEN | awk 'NR==2{print $1" (pid "$2")"}'). Mude API_PORT/WEB_PORT no .env."
      fi
    done
    (
      # Read the root .env before leaving it: after `cd backend`, env_get would
      # read backend/.env and silently drop every setting kept at the root.
      gemini_key="$(env_get GEMINI_API_KEY)"
      profile="$(memory_profile)"
      max_local_models="$(env_get MAX_LOCAL_MODELS)"
      embedding_device="$(env_get EMBEDDING_DEVICE)"
      max_concurrency="$(env_get MAX_EXPERIMENT_CONCURRENCY)"
      allow_swap="$(env_get PERPLEXITY_ALLOW_SWAP)"
      cd backend || exit 1
      # Explicit [::1] everywhere: "localhost" may try 127.0.0.1 first.
      env ${CA_ENV[@]+"${CA_ENV[@]}"} \
      ENV_FILE="" \
      DATABASE_URL="postgresql://ditto:ditto@[::1]:$PG_PORT/ditto" \
      QDRANT_URL="http://[::1]:$QD_PORT" \
      OLLAMA_BASE_URL="$LLM_URL" \
      GEMINI_API_KEY="$gemini_key" \
      MEMORY_PROFILE="$profile" \
      MAX_LOCAL_MODELS="$max_local_models" \
      EMBEDDING_DEVICE="$embedding_device" \
      MAX_EXPERIMENT_CONCURRENCY="$max_concurrency" \
      PERPLEXITY_ALLOW_SWAP="$allow_swap" \
      APP_CONFIG_DIR="$PWD/config" \
      PROMPTS_DIR="$PWD/prompts" \
      nohup ./.venv/bin/uvicorn app.main:app --host ::1 --port "$API_PORT" \
        >"../$RUN_DIR/api.log" 2>&1 &
      echo $! >"../$API_PID"
    )
    wait_http "http://[::1]:$API_PORT/health" 60 "$API_PID" \
      || { tail -n 20 "$RUN_DIR/api.log" >&2; fail "a API não subiu (log acima: $RUN_DIR/api.log)"; }
    ok "rodando em http://[::1]:$API_PORT (log: $RUN_DIR/api.log)"
  fi

  step "Frontend (Vite, host)"
  if alive "$WEB_PID"; then
    ok "já rodando (pid $(cat "$WEB_PID"))"
  else
    (
      cd frontend || exit 1
      VITE_API_PROXY="http://[::1]:$API_PORT" \
      nohup ./node_modules/.bin/vite --host ::1 --port "$WEB_PORT" --strictPort \
        >"../$RUN_DIR/web.log" 2>&1 &
      echo $! >"../$WEB_PID"
    )
    wait_http "http://[::1]:$WEB_PORT/" 60 "$WEB_PID" \
      || { tail -n 20 "$RUN_DIR/web.log" >&2; fail "o frontend não subiu (log acima: $RUN_DIR/web.log)"; }
    wait_http "http://[::1]:$WEB_PORT/api/health" 10 \
      || warn "o frontend não alcança a API pelo proxy (/api/health)"
    ok "rodando (log: $RUN_DIR/web.log)"
  fi

  step "Pronto"
  ok "abra http://localhost:$WEB_PORT   (API: http://[::1]:$API_PORT · LLM: $LLM_URL)"
  ok "parar: make down-local · diagnóstico: make doctor"
}

down() {
  stop_pid "$WEB_PID" && ok "frontend parado" || ok "frontend não estava rodando"
  stop_pid "$API_PID" && ok "API parada" || ok "API não estava rodando"
  docker compose stop postgres qdrant >/dev/null 2>&1 && ok "Postgres e Qdrant parados"
  ok "o servidor de LLM continua rodando (make llm-down para parar)"
}

status() {
  alive "$API_PID" && ok "API rodando (pid $(cat "$API_PID"))" || warn "API parada"
  alive "$WEB_PID" && ok "frontend rodando (pid $(cat "$WEB_PID"))" || warn "frontend parado"
  ./scripts/llm.sh status
}

# Used by `make up`: the Docker api/frontend need the ports back.
stop_apps() {
  stop_pid "$WEB_PID" && ok "frontend local parado (o Docker assume a porta $WEB_PORT)"
  stop_pid "$API_PID" && ok "API local parada (o Docker assume a porta $API_PORT)"
  return 0
}

case "${1:-status}" in
  up) up ;;
  down) down ;;
  stop-apps) stop_apps ;;
  status) status ;;
  *) fail "uso: scripts/local.sh up|down|status" ;;
esac
