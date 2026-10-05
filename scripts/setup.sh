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
fresh_env=0
if [ -f .env ]; then
  ok ".env já existe (mantido como está)"
else
  cp .env.example .env
  fresh_env=1
  ok ".env criado a partir de .env.example"
fi

step "Senha do Postgres"
if [ "$fresh_env" = 1 ]; then
  env_set POSTGRES_PASSWORD "$(generate_password)"
  ok "senha aleatória gerada para o Postgres (POSTGRES_PASSWORD no .env)"
else
  # Instalação existente: nunca troca a senha aqui. O volume do Postgres já
  # foi inicializado com a senha atual (ditto, se a variável nunca existiu);
  # sobrescrever quebraria o login sem recriar o volume.
  ok "mantendo a senha do Postgres já configurada (instalação existente)"
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

step "Memória"
./scripts/memory-profile.sh init
./scripts/memory-profile.sh show

step "Portas"
./scripts/check-ports.sh || warn "resolva as portas antes do 'make up'"

step "Pronto"
echo "  make up          # sobe api:8000, frontend:3000, qdrant:6333, postgres:5432 (portas mudam via .env)"
echo "  make llm-setup   # (opcional) prepara o Ollama para servir a LLM localmente com GPU"
