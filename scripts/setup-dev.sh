#!/usr/bin/env bash
# Development setup: backend venv, frontend packages, graphify (knowledge
# graph + git hooks) and the impeccable design engine. Idempotent: safe to
# re-run after a pull. Works behind corporate VPNs by reusing the host's CAs.
#
#   make setup-dev            everything below
#   LOCAL=1 make setup-dev    also the local embedders (sentence-transformers + torch, ~1 GB)
set -euo pipefail

cd "$(dirname "$0")/.."
. scripts/common.sh

# ---------------------------------------------------------------------------
icloud_warning

step "Certificados (VPN/proxy)"
./scripts/host-certs.sh >/dev/null
host_ca="$PWD/certs/host-ca.pem"
if [ -s "$host_ca" ]; then
  # Node ignores the macOS keychain; npm gets the host CAs explicitly.
  export NODE_EXTRA_CA_CERTS="$host_ca"
  # uv and pip read the OS trust store (keychain on macOS) with these.
  export UV_NATIVE_TLS=1
  ok "CAs do host exportadas para npm, pip e uv"
else
  ok "nenhuma CA extra no host; usando as padrão"
fi

# ---------------------------------------------------------------------------
step "Python do backend"
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if has "$candidate" && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.11+ não encontrado. Instale o Python 3.13 (https://www.python.org/downloads/)."
ok "usando $($PY --version) ($(command -v "$PY"))"

if [ ! -x backend/.venv/bin/python ]; then
  "$PY" -m venv backend/.venv
  ok "venv criado em backend/.venv"
else
  ok "venv já existe em backend/.venv"
fi
VENV_PY="backend/.venv/bin/python"

# pip >= 24.2 verifies TLS with the OS trust store (truststore), which already
# trusts the VPN's root CA. Older pips only know certifi, so give them a bundle
# with the host CAs just for this upgrade.
pip_env=()
if [ -s "$host_ca" ]; then
  bundle="$(mktemp)"
  cat "$("$VENV_PY" -c 'import pip._vendor.certifi as c; print(c.where())')" "$host_ca" >"$bundle"
  pip_env=(PIP_CERT="$bundle")
fi
env ${pip_env[@]+"${pip_env[@]}"} "$VENV_PY" -m pip install --quiet --upgrade pip
extras="dev"
[ "${LOCAL:-0}" = "1" ] && extras="dev,local"
env ${pip_env[@]+"${pip_env[@]}"} "$VENV_PY" -m pip install --quiet -e "backend[$extras]"
ok "backend instalado com os extras [$extras]"
if ! "$VENV_PY" -c 'import sentence_transformers' >/dev/null 2>&1; then
  warn "embedders locais (e5, paraphrase) não instalados; use LOCAL=1 make setup-dev se precisar"
fi

# ---------------------------------------------------------------------------
step "Frontend (Node 22)"
has node || fail "Node não encontrado. Instale o Node 22 (https://nodejs.org)."
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" != "22" ]; then
  warn "Node $(node -v) detectado; o projeto usa Node 22 (pode funcionar, mas não é testado)"
else
  ok "Node $(node -v)"
fi
(cd frontend && npm ci --no-audit --no-fund --loglevel=error)
ok "dependências do frontend instaladas"

# ---------------------------------------------------------------------------
step "graphify (grafo de conhecimento do código)"
if ./scripts/graphify.sh --help >/dev/null 2>&1; then
  ok "graphify já instalado"
elif has uv; then
  uv tool install --quiet graphifyy
  ok "graphify instalado com uv"
elif has pipx; then
  pipx install graphifyy >/dev/null
  ok "graphify instalado com pipx"
else
  # No tool manager: a repo-local venv the wrapper already knows how to find.
  "$PY" -m venv .tools/graphify
  env ${pip_env[@]+"${pip_env[@]}"} .tools/graphify/bin/python -m pip install --quiet --upgrade pip graphifyy
  ok "graphify instalado em .tools/graphify"
fi

# Git hooks (rebuild the graph after commit/checkout) and the graph.json merge
# driver are per-clone settings, so each machine installs its own.
./scripts/graphify.sh hook install >/dev/null
ok "hooks de git e merge driver do graph.json configurados"

PYTHONHASHSEED=0 ./scripts/graphify.sh update . >/dev/null
ok "grafo gerado em graphify-out/"

# ---------------------------------------------------------------------------
step "impeccable (skill de design)"
# The launcher downloads its engine on first use; do it now so the design
# hook is ready before the first edit.
if .claude/skills/impeccable/scripts/impeccable --version >/dev/null 2>&1; then
  ok "engine do impeccable pronta"
else
  warn "não consegui baixar a engine do impeccable agora; ela será baixada no primeiro uso"
fi

# ---------------------------------------------------------------------------
step "Pronto"
ok "testes do backend:  make test"
ok "testes do frontend: make front-test"
ok "subir o sistema:    make setup (1ª vez) e make up"
