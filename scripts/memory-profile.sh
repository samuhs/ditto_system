#!/usr/bin/env bash
# Shows or switches the memory profile (MEMORY_PROFILE in .env).
#   low      - up to 8 GB of RAM: 1 local model at a time, embedders on CPU, less parallelism
#   standard - more RAM: up to 3 local models, embedders on the GPU when the LLM leaves it free
# Usage: scripts/memory-profile.sh show | set low|standard | init | hint-up
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

describe() {
  case "$1" in
    low)
      echo "  low: 1 modelo local na memória por vez, embeddings na CPU, até 2 perguntas em paralelo,"
      echo "  cache de prompts do MLX limitado (2 entradas, 512 MB) e containers com limite de memória."
      echo "  Experimentos mais lentos, mas a RAM não estoura." ;;
    standard)
      echo "  standard: até 3 modelos locais na memória, embeddings na GPU quando o LLM não a usa,"
      echo "  até 32 perguntas em paralelo. Mais rápido; pode usar swap se a RAM não comportar." ;;
  esac
}
other() { if [ "$1" = low ]; then echo standard; else echo low; fi; }

# Records the profile in .env, with the Compose override that goes with it.
record() {
  env_set MEMORY_PROFILE "$1"
  # Setups before the memory profiles pinned MLX_PARALLEL=4 on their own; as an
  # explicit value it would override the profile, so the old default goes.
  if [ "$(env_file_get MLX_PARALLEL)" = 4 ]; then
    env_unset MLX_PARALLEL
    ok "removido MLX_PARALLEL=4 do .env (valor antigo automático; agora o perfil decide)"
  fi
  if [ "$1" = low ]; then
    env_set COMPOSE_FILE "docker-compose.yml:docker-compose.low-memory.yml"
  else
    env_unset COMPOSE_FILE
  fi
}

show() {
  local p ram; p="$(memory_profile)"; ram="$(total_ram_bytes)"
  step "Perfil de memória: $p"
  if [ -n "$ram" ]; then
    ok "RAM desta máquina: $(( (ram + 536870912) / 1073741824 )) GB (perfil sugerido: $(detect_memory_profile))"
  fi
  describe "$p"
  echo "  Para trocar: make memory-profile PROFILE=$(other "$p")"
}

case "${1:-show}" in
  show) show ;;
  set)
    p="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
    case "$p" in
      low|standard) ;;
      *) fail "perfil inválido: '${2:-}'. Use: make memory-profile PROFILE=low ou PROFILE=standard" ;;
    esac
    record "$p"
    ok ".env: MEMORY_PROFILE=$p"
    describe "$p"
    if curl -sf "$(./scripts/llm.sh url)/models" >/dev/null 2>&1; then
      step "Reiniciando o servidor de LLM com o perfil novo"
      ./scripts/llm.sh down || true
      ./scripts/llm.sh up
    fi
    step "Falta reiniciar a API para o perfil valer"
    echo "  make up         # tudo no Docker"
    echo "  make up-local   # ou API e front no host (recomendado no perfil low)"
    ;;
  init)
    # First run on this machine: record the detected profile and say how to change it.
    if [ -z "$(env_file_get MEMORY_PROFILE)" ]; then
      p="$(detect_memory_profile)"
      record "$p"
      ok "perfil de memória: $p (detectado pela RAM). Para trocar: make memory-profile PROFILE=$(other "$p")"
    fi
    ;;
  hint-up)
    if [ "$(memory_profile)" = low ]; then
      warn "perfil de memória low: recomendado 'make up-local' (sem a VM do Docker para a API, sobra RAM para o LLM)."
      warn "para trocar o perfil: make memory-profile PROFILE=standard"
    fi
    ;;
  *) fail "uso: scripts/memory-profile.sh show | set low|standard | init | hint-up" ;;
esac
