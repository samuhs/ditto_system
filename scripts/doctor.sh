#!/usr/bin/env bash
# Tests every network hop Ditto relies on and says which run mode fits this
# machine: `make up` (everything in Docker) or `make up-local` (API and
# frontend on the host over IPv6 loopback). Read-only: starts nothing.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

port() { local v; v="$(env_get "$1")"; echo "${v:-$2}"; }
API_PORT="$(port API_PORT 8000)"
PG_PORT="$(port POSTGRES_PORT 5432)"
QD_PORT="$(port QDRANT_PORT 6333)"

PY="$(command -v python3)"
[ -x backend/.venv/bin/python ] && PY="backend/.venv/bin/python"

# tcp HOST PORT -> prints "ok" or the socket error
tcp() {
  "$PY" - "$1" "$2" <<'PY'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
family = socket.AF_INET6 if ":" in host else socket.AF_INET
s = socket.socket(family)
s.settimeout(3)
try:
    s.connect((host, port))
    print("ok")
except OSError as e:
    print(f"{e.strerror or e} (errno {e.errno})")
PY
}
check() {
  # check "label" result-string [hint]
  if [ "$2" = ok ]; then ok "$1"; else warn "$1: $2${3:+ — $3}"; fi
}

step "Loopback do macOS/Linux"
ipv4_bad=0
if ipv4_loopback_broken; then
  ipv4_bad=1
  warn "IPv4 127.0.0.1: BLOQUEADO (errno 49, provável agente de VPN/segurança)"
else
  ok "IPv4 127.0.0.1 funciona"
fi
v6="$("$PY" - <<'PY'
import socket
srv = socket.socket(socket.AF_INET6); srv.bind(("::1", 0)); srv.listen(1)
c = socket.socket(socket.AF_INET6); c.settimeout(3)
try:
    c.connect(("::1", srv.getsockname()[1])); print("ok")
except OSError as e:
    print(f"{e.strerror} (errno {e.errno})")
PY
)"
check "IPv6 [::1] funciona" "$v6"

step "Docker (Postgres e Qdrant)"
if docker info >/dev/null 2>&1; then
  ok "Docker respondendo"
  if [ -n "$(docker compose ps -q postgres 2>/dev/null)" ]; then
    check "Postgres via [::1]:$PG_PORT" "$(tcp ::1 "$PG_PORT")"
    [ "$ipv4_bad" = 0 ] && check "Postgres via 127.0.0.1:$PG_PORT" "$(tcp 127.0.0.1 "$PG_PORT")"
  else
    warn "Postgres não está rodando (make up ou make up-local)"
  fi
  if [ -n "$(docker compose ps -q qdrant 2>/dev/null)" ]; then
    check "Qdrant via [::1]:$QD_PORT" "$(tcp ::1 "$QD_PORT")"
  fi
else
  warn "Docker não responde (abra o Docker Desktop)"
fi

step "Servidor de LLM ($(llm_server))"
case "$(llm_server)" in
  mlx)
    if pgrep -f "mlx_lm.server .*--port $(mlx_port)" >/dev/null; then
      bound="$(cat "$MLX_DIR/server.host" 2>/dev/null || echo '?')"
      ok "MLX rodando, escutando em $bound:$(mlx_port)"
      case "$bound" in *:*) check "MLX via [::1]" "$(tcp ::1 "$(mlx_port)")" ;;
        *) check "MLX via 127.0.0.1" "$(tcp 127.0.0.1 "$(mlx_port)")" ;; esac
    else
      warn "MLX parado (make llm-up ou make up-local)"
    fi
    ;;
  host)
    check "Ollama nativo via 127.0.0.1:11434" "$(tcp 127.0.0.1 11434)" \
      "o Ollama nativo depende do 127.0.0.1 internamente; nesta máquina use MLX ou LLM_SERVER=docker"
    ;;
  docker)
    check "Ollama do Docker via [::1]:$(port OLLAMA_DOCKER_PORT 11435)" "$(tcp ::1 "$(port OLLAMA_DOCKER_PORT 11435)")"
    ;;
esac

step "API"
if [ -f .tools/local/api.pid ] && kill -0 "$(cat .tools/local/api.pid)" 2>/dev/null; then
  check "API local (make up-local) em [::1]:$API_PORT/health" \
    "$(curl -sf -o /dev/null "http://[::1]:$API_PORT/health" && echo ok || echo 'sem resposta (.tools/local/api.log)')"
elif [ -n "$(docker compose ps -q api 2>/dev/null)" ]; then
  check "API no Docker via localhost:$API_PORT/health" \
    "$(curl -sf -o /dev/null "http://localhost:$API_PORT/health" && echo ok || echo 'sem resposta')"
  if [ "$(llm_server)" != docker ]; then
    llm_port=11434; [ "$(llm_server)" = mlx ] && llm_port="$(mlx_port)"
    reach="$(docker compose exec -T api python -c "
import socket
s = socket.socket(); s.settimeout(3)
try:
    s.connect(('host.docker.internal', $llm_port)); print('ok')
except OSError as e:
    print(f'{e.strerror} (errno {e.errno})')" 2>/dev/null)"
    check "container da API → servidor de LLM no host" "${reach:-falhou}" \
      "o Docker não alcança o host aqui; use make up-local"
  fi
else
  warn "API não está rodando"
fi

step "Internet (HTTPS com as CAs do host)"
check "Hugging Face (modelos)" "$(curl -sf -o /dev/null --max-time 10 https://huggingface.co && echo ok || echo 'falhou')"
check "PyPI (pacotes Python)" "$(curl -sf -o /dev/null --max-time 10 https://pypi.org/simple/pip/ && echo ok || echo 'falhou')"
check "npm registry" "$(curl -sf -o /dev/null --max-time 10 https://registry.npmjs.org/react && echo ok || echo 'falhou')"

step "Arquivos do projeto"
if in_icloud; then
  icloud_warning
  evicted=0
  for d in backend/.venv frontend/node_modules "$MLX_DIR"; do
    [ -d "$d" ] || continue
    n="$(find "$d" -flags +dataless 2>/dev/null | wc -l | tr -d ' ')"
    [ "$n" -gt 0 ] && { warn "$n arquivo(s) de $d estão só na nuvem (podem travar ao abrir)"; evicted=1; }
  done
  [ "$evicted" = 0 ] && ok "nenhum arquivo das dependências fora do disco, por enquanto"
else
  ok "projeto fora do iCloud"
fi

step "Recomendação"
if [ "$ipv4_bad" = 1 ]; then
  ok "use 'make up-local' (API e front no host, tudo por IPv6) com LLM_SERVER=mlx"
  ok "'make up' deixa a API no Docker sem acesso a um servidor de LLM no host"
else
  ok "'make up' funciona nesta máquina; 'make up-local' também é uma opção"
fi

./scripts/memory-profile.sh show
./scripts/memory-profile.sh hint-up
