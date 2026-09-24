#!/usr/bin/env bash
# Manage models on the Ollama server: add | rm | list. The app lists them live.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

cmd="${1:-}"
model="${2:-}"
if [ "$(llm_server)" = docker ]; then
  ollama_cli list >/dev/null 2>&1 || fail "o Ollama do Docker não está rodando. Rode 'make up'."
else
  has ollama || fail "ollama não está instalado. Rode 'make llm-setup' primeiro."
  ollama list >/dev/null 2>&1 || fail "o Ollama não está rodando. Rode 'make ollama-up'."
fi

case "$cmd" in
  add)
    [ -n "$model" ] || fail "informe o modelo: make model-add qwen3:1.7b"
    step "Baixando $model"
    ollama_cli pull "$model"
    ok "disponível no app (Gerar teste e Chat) como '$model'"
    ;;
  rm)
    [ -n "$model" ] || fail "informe o modelo: make model-rm qwen3:1.7b"
    step "Removendo $model"
    if ollama_cli list | awk 'NR>1{print $1}' | grep -Fxq "$model" \
      || ollama_cli list | awk 'NR>1{print $1}' | grep -Fxq "$model:latest"; then
      ollama_cli rm "$model"
      ok "removido (some da lista do app)"
    else
      ok "não estava baixado no Ollama"
    fi
    ;;
  list)
    ollama_cli list
    ;;
  *) fail "uso: scripts/model.sh add|rm|list [modelo]" ;;
esac
