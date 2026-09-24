#!/usr/bin/env bash
# Builds on the host what the Docker builds would otherwise download:
#   - frontend/dist (npm ci + npm run build), marked with frontend/.host-build;
#   - the CPU torch wheel for the container's platform, in backend/wheels/.
#
# Why: some corporate networks let the host reach npm/PyTorch but filter or
# time out the containers' egress (ECONNREFUSED / ReadTimeout during builds).
# Every step is best-effort: when the host lacks Node/Python or a download
# fails, the step is skipped and the Dockerfile downloads it as before.
#
# Env: SKIP_HOST_BUILD=1 skips everything (container builds download all);
#      TORCH_VERSION=2.x.y pins the wheel (default: latest CPU build).
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

host_ca="$PWD/certs/host-ca.pem"

skip_frontend() {
  rm -f frontend/.host-build
  warn "$1; o frontend será compilado dentro do container"
}

if [ "${SKIP_HOST_BUILD:-0}" = "1" ]; then
  rm -f frontend/.host-build
  ok "SKIP_HOST_BUILD=1: os containers baixam e compilam tudo"
  exit 0
fi

# ---------------------------------------------------------------------------
# Frontend: build on the host, the image only serves it.
if ! has node || ! has npm; then
  skip_frontend "Node não encontrado no host"
else
  [ -s "$host_ca" ] && export NODE_EXTRA_CA_CERTS="$host_ca"
  lock=frontend/package-lock.json
  stamp=frontend/node_modules/.package-lock.json
  ok_modules=1
  if [ ! -f "$stamp" ] || [ "$lock" -nt "$stamp" ]; then
    (cd frontend && npm ci --no-audit --no-fund --loglevel=error) || ok_modules=0
  fi
  if [ "$ok_modules" = 0 ]; then
    skip_frontend "npm ci falhou no host"
  elif (cd frontend && npm run build >/tmp/ditto-front-build.log 2>&1); then
    date -u +%Y-%m-%dT%H:%M:%SZ >frontend/.host-build
    ok "frontend compilado no host (frontend/dist)"
  else
    tail -n 20 /tmp/ditto-front-build.log >&2
    fail "o build do frontend falhou (veja acima); corrija antes de subir"
  fi
fi

# ---------------------------------------------------------------------------
# torch: fetch the container-platform wheel on the host (~150 MB, once).
case "$(docker version --format '{{.Server.Arch}}' 2>/dev/null)" in
  arm64 | aarch64) arch=aarch64 ;;
  amd64 | x86_64) arch=x86_64 ;;
  *) arch="" ;;
esac

PY=""
for candidate in backend/.venv/bin/python python3; do
  if [ -x "$candidate" ] || has "$candidate"; then
    if "$candidate" -m pip --version >/dev/null 2>&1; then PY="$candidate"; break; fi
  fi
done

mkdir -p backend/wheels
if [ -z "$arch" ]; then
  warn "não consegui ler a arquitetura do Docker; o torch será baixado dentro do container"
elif ls backend/wheels/torch-*"$arch".whl >/dev/null 2>&1; then
  ok "wheel do torch já disponível ($(basename backend/wheels/torch-*"$arch".whl | head -1))"
elif [ -z "$PY" ]; then
  warn "pip não encontrado no host; o torch será baixado dentro do container"
else
  pip_env=()
  if [ -s "$host_ca" ]; then
    bundle="$(mktemp)"
    cat "$("$PY" -c 'import pip._vendor.certifi as c; print(c.where())')" "$host_ca" >"$bundle"
    pip_env=(PIP_CERT="$bundle")
  fi
  spec="torch${TORCH_VERSION:+==$TORCH_VERSION}"
  echo "  baixando $spec para linux/$arch (uma vez, ~150 MB)..."
  # Must match the image's Python (python:3.11-slim).
  if env ${pip_env[@]+"${pip_env[@]}"} "$PY" -m pip download "$spec" \
      --quiet --no-deps --only-binary=:all: \
      --python-version 3.11 --implementation cp --abi cp311 \
      --platform "manylinux_2_28_$arch" --platform "manylinux2014_$arch" --platform "linux_$arch" \
      --index-url https://download.pytorch.org/whl/cpu \
      --timeout 120 --retries 5 \
      -d backend/wheels; then
    ok "wheel do torch baixado em backend/wheels/"
  else
    warn "o download do torch falhou no host; o container vai tentar baixar"
  fi
fi
