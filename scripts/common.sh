# Shared helpers for the setup scripts. Source it; do not execute it.

if [ -t 1 ]; then
  _B=$'\033[1m' _G=$'\033[32m' _Y=$'\033[33m' _R=$'\033[31m' _N=$'\033[0m'
else
  _B='' _G='' _Y='' _R='' _N=''
fi

step() { printf '\n%s==> %s%s\n' "$_B" "$*" "$_N"; }
ok()   { printf '  %s✓%s %s\n' "$_G" "$_N" "$*"; }
warn() { printf '  %s!%s %s\n' "$_Y" "$_N" "$*"; }
fail() { printf '  %s✗%s %s\n' "$_R" "$_N" "$*" >&2; exit 1; }

# confirm "question" -> 0 on yes. YES=1 answers yes; no TTY answers no.
confirm() {
  if [ "${YES:-0}" = "1" ]; then return 0; fi
  if [ ! -t 0 ]; then return 1; fi
  printf '  ? %s [s/N] ' "$1"
  read -r _ans
  case "$_ans" in s|S|sim|y|Y|yes) return 0 ;; *) return 1 ;; esac
}

has() { command -v "$1" >/dev/null 2>&1; }

# .env helpers. env_file_get reads only .env; env_get the environment first.
env_file_get() {
  [ -f .env ] || return 0
  local v; v="$(sed -n "s/^$1=//p" .env | tail -1)"
  v="${v%\"}"; v="${v#\"}"
  printf '%s' "$v"
}
env_get() {
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f .env ]; then
    v="$(sed -n "s/^$1=//p" .env | tail -1)"
    v="${v%\"}"; v="${v#\"}"
  fi
  printf '%s' "$v"
}
env_set() {
  [ -f .env ] || cp .env.example .env
  local tmp; tmp="$(mktemp)"
  grep -v "^$1=" .env >"$tmp" || true
  printf '%s=%s\n' "$1" "$2" >>"$tmp"
  mv "$tmp" .env
}
env_unset() {
  [ -f .env ] || return 0
  local tmp; tmp="$(mktemp)"
  grep -v "^$1=" .env >"$tmp" || true
  mv "$tmp" .env
}

# Where the LLM server runs, as recorded in .env by `make llm-setup`:
#   mlx    - Apple MLX on the host (Metal GPU, fastest on Apple Silicon)
#   host   - native Ollama on the host (GPU)
#   docker - Ollama in a container (CPU on macOS; immune to VPNs that break
#            host loopback)
# .env is the only source of truth here: LLM_SERVER on the command line is a
# request to llm-setup, not the server currently running.
llm_server() {
  case "$(env_file_get LLM_SERVER)" in docker) echo docker ;; mlx) echo mlx ;; *) echo host ;; esac
}

# The server new setups get: MLX on Apple Silicon, native Ollama elsewhere.
default_llm_server() {
  if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then echo mlx; else echo host; fi
}

# The ollama CLI of the active server.
ollama_cli() {
  if [ "$(llm_server)" = docker ]; then
    docker compose exec -T ollama ollama "$@"
  else
    ollama "$@"
  fi
}

# --- MLX (Apple Silicon) -----------------------------------------------------
# Outside the repo on purpose: a project under an iCloud-synced folder
# (Desktop/Documents) gets venv files evicted to the cloud, and a timed-out
# on-demand download stalls the server's startup. DITTO_HOME moves it.
MLX_DIR="${DITTO_HOME:-$HOME/.ditto}/mlx"
MLX_PY="$MLX_DIR/bin/python"
mlx_port() { local p; p="$(env_get MLX_PORT)"; echo "${p:-11436}"; }
# 127.0.0.1 so the API container reaches it via host.docker.internal; `make
# up-local` uses ::1 instead (IPv6 loopback survives VPNs that break IPv4).
mlx_host() { local h; h="$(env_get MLX_HOST)"; echo "${h:-127.0.0.1}"; }
mlx_url() {
  case "$(mlx_host)" in
    *:*) echo "http://[$(mlx_host)]:$(mlx_port)" ;;
    *) echo "http://localhost:$(mlx_port)" ;;
  esac
}
mlx_up() { curl -sf "$(mlx_url)/v1/models" >/dev/null 2>&1; }

# Short names are MLX community conversions: Qwen2.5-7B-Instruct-4bit ->
# mlx-community/Qwen2.5-7B-Instruct-4bit. Full Hugging Face ids pass through.
mlx_model_id() {
  case "$1" in */*) echo "$1" ;; *) echo "mlx-community/$1" ;; esac
}

# Python in the MLX venv trusts the host CAs too (Hugging Face downloads
# behind VPNs that inspect HTTPS).
mlx_env() {
  local ca="certs/host-ca.pem" bundle="$MLX_DIR/ca-bundle.pem"
  if [ -s "$ca" ] && [ -x "$MLX_PY" ]; then
    cat "$("$MLX_PY" -c 'import certifi; print(certifi.where())')" "$ca" >"$bundle" 2>/dev/null \
      && export SSL_CERT_FILE="$bundle" REQUESTS_CA_BUNDLE="$bundle"
  fi
  return 0
}

# Some corporate VPN/security agents on macOS break outgoing IPv4 loopback
# connections ("Can't assign requested address", errno 49).
ipv4_loopback_broken() {
  [ "$(uname -s)" = Darwin ] && has python3 || return 1
  python3 - <<'PY' 2>/dev/null
import errno, socket, sys
s = socket.socket()
s.settimeout(1)
try:
    s.connect(("127.0.0.1", 1))
except OSError as e:
    sys.exit(0 if e.errno == errno.EADDRNOTAVAIL else 1)
sys.exit(1)
PY
}

# True when the project sits in an iCloud Drive synced folder (macOS
# "Desktop & Documents in iCloud"), where venv and node_modules files can be
# evicted to the cloud and time out when read.
in_icloud() {
  [ "$(uname -s)" = Darwin ] || return 1
  local dir="$PWD"
  while [ "$dir" != "/" ] && [ "$dir" != "$HOME" ]; do
    xattr -p com.apple.file-provider-domain-id "$dir" 2>/dev/null | grep -q CloudDocs && return 0
    dir="$(dirname "$dir")"
  done
  return 1
}
icloud_warning() {
  in_icloud || return 0
  warn "o projeto está numa pasta sincronizada pelo iCloud ($PWD)"
  warn "o macOS pode tirar do disco arquivos do venv/node_modules e travar a inicialização"
  warn "recomendado: mover o projeto para fora da Mesa/Documentos (ex.: ~/doutorado)"
}

# Undo what the previous `make llm-setup` mode left behind before switching.
reset_llm_server() {
  case "$(env_file_get LLM_SERVER)" in
    docker) docker compose --profile ollama-docker rm -sf ollama >/dev/null 2>&1 || true ;;
    mlx) ./scripts/llm.sh down >/dev/null 2>&1 || true ;;  # .env still says mlx here
  esac
  for key in LLM_SERVER COMPOSE_PROFILES OLLAMA_BASE_URL OLLAMA_NUM_PARALLEL OLLAMA_MODELS_DIR MLX_PARALLEL; do
    env_unset "$key"
  done
  unset COMPOSE_PROFILES OLLAMA_BASE_URL
}

# --- Memory profile ------------------------------------------------------------
# low (<= 8 GB of RAM) or standard, stored as MEMORY_PROFILE in .env.
# See docs/superpowers/specs/2026-09-24-gestao-de-memoria-design.md.
total_ram_bytes() {
  case "$(uname -s)" in
    Darwin) sysctl -n hw.memsize 2>/dev/null ;;
    Linux) awk '/^MemTotal:/ {printf "%d\n", $2 * 1024}' /proc/meminfo 2>/dev/null ;;
  esac
}
detect_memory_profile() {
  local ram; ram="$(total_ram_bytes)"
  if [ -n "$ram" ] && [ "$ram" -le 9000000000 ]; then echo low; else echo standard; fi
}
memory_profile() {
  case "$(env_get MEMORY_PROFILE | tr '[:upper:]' '[:lower:]' | tr -d ' ')" in
    low) echo low ;; standard) echo standard ;; *) detect_memory_profile ;;
  esac
}
# profile_value LOW STANDARD -> the one for the active profile
profile_value() { if [ "$(memory_profile)" = low ]; then echo "$1"; else echo "$2"; fi; }
# Extra Ollama variables of the active profile, one KEY=VALUE per line.
ollama_profile_vars() {
  [ "$(memory_profile)" = low ] || return 0
  printf '%s\n' OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0
}
