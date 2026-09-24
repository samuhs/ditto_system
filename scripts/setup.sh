#!/usr/bin/env bash
# Prepares a fresh clone to run the Docker stack: checks Docker, creates .env,
# asks for the optional Gemini key and warns about busy ports.
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

step "Docker"
has docker || fail "Docker não encontrado. Instale: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 não encontrado (comando 'docker compose')."
docker info >/dev/null 2>&1 || fail "O daemon do Docker não está respondendo. Abra o Docker Desktop ou rode 'sudo systemctl start docker'."
ok "$(docker compose version)"

step "Arquivo .env"
if [ -f .env ]; then
  ok ".env já existe (mantido como está)"
else
  cp .env.example .env
  ok ".env criado a partir de .env.example"
fi

current_key=$(sed -n 's/^GEMINI_API_KEY=//p' .env | head -1)
if [ -n "$current_key" ]; then
  ok "GEMINI_API_KEY configurada"
else
  warn "GEMINI_API_KEY vazia. Ela é opcional: sem ela use Ollama + embedders locais (e5, paraphrase),"
  warn "ou configure depois na tela Configurações."
  if [ -t 0 ] && [ "${YES:-0}" != "1" ]; then
    printf '  ? Cole sua chave Gemini (Enter para pular): '
    read -rs key
    echo
    if [ -n "$key" ]; then
      tmp=$(mktemp)
      if grep -q '^GEMINI_API_KEY=' .env; then
        awk -v k="$key" '/^GEMINI_API_KEY=/{print "GEMINI_API_KEY=" k; next} {print}' .env >"$tmp"
      else
        cat .env >"$tmp"
        printf 'GEMINI_API_KEY=%s\n' "$key" >>"$tmp"
      fi
      mv "$tmp" .env
      ok "GEMINI_API_KEY salva no .env"
    fi
  fi
fi

step "Portas"
if [ -n "$(docker compose ps -q 2>/dev/null)" ]; then
  ok "stack já está rodando (portas em uso por ele)"
elif has lsof; then
  busy=0
  for port in 3000 8000 5432 6333; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "porta $port já está em uso por outro processo"
      busy=1
    fi
  done
  [ "$busy" = 0 ] && ok "3000, 8000, 5432 e 6333 livres"
else
  warn "lsof não disponível; pulei a checagem de portas"
fi

step "Pronto"
echo "  make up          # sobe api:8000, frontend:3000, qdrant:6333, postgres:5432"
echo "  make llm-setup   # (opcional) prepara o Ollama para servir a LLM localmente com GPU"
