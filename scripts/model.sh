#!/usr/bin/env bash
# Manage models on the Ollama server and in the app: add | rm | list.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

cmd="${1:-}"
model="${2:-}"
has ollama || fail "ollama não está instalado. Rode 'make llm-setup' primeiro."
curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 || fail "o Ollama não está rodando. Rode 'make ollama-up'."

case "$cmd" in
  add)
    [ -n "$model" ] || fail "informe o modelo: make model-add qwen3:1.7b"
    step "Baixando $model"
    ollama pull "$model"
    ok "$(python3 scripts/app_models.py add "$model" ${OLLAMA_ID:+"$OLLAMA_ID"})"
    ;;
  rm)
    [ -n "$model" ] || fail "informe o modelo: make model-rm qwen3:1.7b"
    step "Removendo $model"
    ok "$(python3 scripts/app_models.py remove "$model")"
    if ollama list | awk 'NR>1{print $1}' | grep -Fxq "$model" \
      || ollama list | awk 'NR>1{print $1}' | grep -Fxq "$model:latest"; then
      ollama rm "$model"
    else
      ok "não estava baixado no Ollama"
    fi
    ;;
  list)
    step "Baixados no Ollama"
    ollama list
    step "Registrados no app"
    python3 scripts/app_models.py list
    ;;
  *) fail "uso: scripts/model.sh add|rm|list [modelo]" ;;
esac
