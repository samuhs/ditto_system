#!/usr/bin/env bash
# Manage models on the Ollama server: add | rm | list. The app lists them live.
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
    ok "disponível no app (Gerar teste e Chat) como '$model'"
    ;;
  rm)
    [ -n "$model" ] || fail "informe o modelo: make model-rm qwen3:1.7b"
    step "Removendo $model"
    if ollama list | awk 'NR>1{print $1}' | grep -Fxq "$model" \
      || ollama list | awk 'NR>1{print $1}' | grep -Fxq "$model:latest"; then
      ollama rm "$model"
      ok "removido (some da lista do app)"
    else
      ok "não estava baixado no Ollama"
    fi
    ;;
  list)
    ollama list
    ;;
  *) fail "uso: scripts/model.sh add|rm|list [modelo]" ;;
esac
