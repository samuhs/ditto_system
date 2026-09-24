#!/usr/bin/env bash
# Start, stop or locate the LLM server chosen by `make llm-setup`.
#   llm.sh up      start it if it is not running (make up calls this)
#   llm.sh down    stop it
#   llm.sh status  say where it runs and whether it answers
#   llm.sh url     print its OpenAI-compatible base URL as seen from the host
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

MLX_PID="$MLX_DIR/server.pid"
MLX_LOG="$MLX_DIR/server.log"
MLX_HOST_FILE="$MLX_DIR/server.host"   # the address the running server is bound to
mlx_pattern() { echo "mlx_lm.server --host .* --port $(mlx_port)"; }

mlx_start() {
  if pgrep -f "$(mlx_pattern)" >/dev/null; then
    if [ "$(cat "$MLX_HOST_FILE" 2>/dev/null)" = "$(mlx_host)" ] && mlx_up; then
      ok "MLX já está rodando em $(mlx_url)"
      return 0
    fi
    mlx_stop >/dev/null   # bound to another address: restart on the requested one
  fi
  [ -x "$MLX_DIR/bin/mlx_lm.server" ] || fail "MLX não instalado. Rode: make llm-setup"
  mlx_env
  local parallel; parallel="$(env_get MLX_PARALLEL)"
  # Loopback only (see mlx_host): never exposed to the network.
  nohup "$MLX_DIR/bin/mlx_lm.server" --host "$(mlx_host)" --port "$(mlx_port)" \
    --decode-concurrency "${parallel:-4}" --max-tokens 1024 \
    >"$MLX_LOG" 2>&1 &
  echo $! >"$MLX_PID"
  mlx_host >"$MLX_HOST_FILE"
  # Startup imports MLX and transformers: seconds normally, minutes on a
  # machine short of memory.
  for i in $(seq 1 180); do
    [ "$i" = 30 ] && echo "  ainda iniciando o MLX (máquina com pouca memória livre?)..."
    mlx_up && { ok "MLX rodando em $(mlx_url) (log: $MLX_LOG)"; return 0; }
    kill -0 "$(cat "$MLX_PID")" 2>/dev/null || break
    sleep 1
  done
  tail -n 20 "$MLX_LOG" >&2
  fail "o servidor MLX não subiu (log acima)"
}

mlx_stop() {
  [ -f "$MLX_PID" ] && kill "$(cat "$MLX_PID")" 2>/dev/null
  pkill -f "$(mlx_pattern)" 2>/dev/null
  rm -f "$MLX_PID" "$MLX_HOST_FILE"
  # Wait for the port to be released so an immediate restart can bind it.
  for _ in $(seq 1 15); do
    pgrep -f "$(mlx_pattern)" >/dev/null || { ok "MLX parado"; return 0; }
    sleep 1
  done
  pkill -9 -f "$(mlx_pattern)" 2>/dev/null
  ok "MLX parado (forçado)"
}

ollama_host_start() {
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama já está rodando"
    return 0
  fi
  has ollama || fail "ollama não instalado. Rode: make llm-setup LLM_SERVER=host"
  local parallel; parallel="$(env_get PARALLEL)"
  export OLLAMA_NUM_PARALLEL="${parallel:-4}"
  [ "$(uname -s)" = Linux ] && export OLLAMA_HOST=0.0.0.0:11434
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && { ok "Ollama pronto"; return 0; }
    sleep 1
  done
  fail "o Ollama não respondeu em 30s (/tmp/ollama.log)"
}

mode="$(llm_server)"
case "${1:-status}" in
  up)
    case "$mode" in
      mlx) mlx_start ;;
      host) ollama_host_start ;;
      docker) docker compose up -d ollama >/dev/null && ok "Ollama do Docker rodando" ;;
    esac
    ;;
  down)
    case "$mode" in
      mlx) mlx_stop ;;
      host) pkill -f "ollama serve" && ok "Ollama parado" || ok "nenhum 'ollama serve' rodando" ;;
      docker) docker compose stop ollama >/dev/null && ok "Ollama do Docker parado" ;;
    esac
    ;;
  url)
    case "$mode" in
      mlx) echo "$(mlx_url)/v1" ;;
      host) echo "http://localhost:11434/v1" ;;
      docker) echo "http://localhost:$(env_get OLLAMA_DOCKER_PORT | grep . || echo 11435)/v1" ;;
    esac
    ;;
  status)
    url="$("$0" url)"
    if curl -sf "${url}/models" >/dev/null 2>&1; then
      ok "servidor de LLM: $mode, respondendo em $url"
    else
      warn "servidor de LLM: $mode, sem resposta em $url (make llm-up)"
    fi
    ;;
  *) fail "uso: scripts/llm.sh up|down|status|url" ;;
esac
