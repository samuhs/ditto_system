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
