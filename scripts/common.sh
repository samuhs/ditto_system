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

# Where the LLM server runs: "host" (native Ollama, GPU) or "docker"
# (Ollama container, CPU on macOS; immune to VPNs that break host loopback).
llm_server() {
  case "$(env_get LLM_SERVER)" in docker) echo docker ;; *) echo host ;; esac
}

# The ollama CLI of the active server.
ollama_cli() {
  if [ "$(llm_server)" = docker ]; then
    docker compose exec -T ollama ollama "$@"
  else
    ollama "$@"
  fi
}
