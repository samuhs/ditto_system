#!/usr/bin/env bash
# Manage models on the active LLM server: add | rm | list. The app lists them live.
#   MLX:    make model-add Qwen2.5-7B-Instruct-4bit   (= mlx-community/Qwen2.5-7B-Instruct-4bit)
#           make model-add org/any-mlx-model          (any Hugging Face id)
#   Ollama: make model-add qwen3:1.7b
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

cmd="${1:-}"
model="${2:-}"
[ "$cmd" = add ] || [ "$cmd" = rm ] || [ "$cmd" = list ] || fail "uso: scripts/model.sh add|rm|list [modelo]"
if [ "$cmd" != list ] && [ -z "$model" ]; then
  fail "informe o modelo: make model-$cmd <modelo>"
fi

# ---------------------------------------------------------------------------
if [ "$(llm_server)" = mlx ]; then
  [ -x "$MLX_PY" ] || fail "MLX não instalado. Rode 'make llm-setup' primeiro."
  mlx_env
  case "$cmd" in
    add)
      id="$(mlx_model_id "$model")"
      step "Baixando $id"
      if ! out="$("$MLX_DIR/bin/hf" download "$id" 2>&1)"; then
        echo "$out" | grep -v '^\s*$' | tail -n 3 >&2
        if echo "$out" | grep -qiE "not found|404|Repository Not Found"; then
          fail "não achei '$id' no Hugging Face. Modelos MLX prontos: https://huggingface.co/mlx-community"
        fi
        fail "o download de '$id' falhou (erro acima)"
      fi
      ok "disponível no app (Gerar teste e Chat) como '$id'"
      ;;
    rm)
      id="$(mlx_model_id "$model")"
      step "Removendo $id"
      MODEL_ID="$id" "$MLX_PY" - <<'PY'
import os
from huggingface_hub import scan_cache_dir

info = scan_cache_dir()
revs = [r.commit_hash for repo in info.repos if repo.repo_id == os.environ["MODEL_ID"] for r in repo.revisions]
if revs:
    info.delete_revisions(*revs).execute()
    print("  ✓ removido (some da lista do app)")
else:
    print("  ✓ não estava baixado")
PY
      ;;
    list)
      ./scripts/llm.sh up >/dev/null
      curl -sf "$(mlx_url)/v1/models" | "$MLX_PY" -c '
import json, sys
for m in json.load(sys.stdin)["data"]:
    print(m["id"])'
      ;;
  esac
  exit 0
fi

# ---------------------------------------------------------------------------
# Ollama (native or in Docker)
if [ "$(llm_server)" = docker ]; then
  ollama_cli list >/dev/null 2>&1 || fail "o Ollama do Docker não está rodando. Rode 'make up'."
else
  has ollama || fail "ollama não está instalado. Rode 'make llm-setup' primeiro."
  ollama list >/dev/null 2>&1 || fail "o Ollama não está rodando. Rode 'make llm-up'."
fi

case "$cmd" in
  add)
    step "Baixando $model"
    ollama_cli pull "$model"
    ok "disponível no app (Gerar teste e Chat) como '$model'"
    ;;
  rm)
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
esac
