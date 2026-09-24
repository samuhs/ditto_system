#!/usr/bin/env bash
# Portable graphify launcher for this repo's hooks and scripts.
#
# Finds graphify wherever `make setup-dev` (or the user) installed it: PATH,
# ~/.local/bin (uv/pipx tools), or the repo-local fallback in .tools/.
# When graphify is missing, the Claude Code hook-guard calls exit quietly so
# sessions keep working on machines that have not run `make setup-dev`.
root="$(cd "$(dirname "$0")/.." && pwd)"

for candidate in \
  "$(command -v graphify 2>/dev/null)" \
  "$HOME/.local/bin/graphify" \
  "$root/.tools/graphify/bin/graphify"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    exec "$candidate" "$@"
  fi
done

if [ "${1:-}" = "hook-guard" ]; then
  exit 0
fi
echo "graphify não encontrado. Rode: make setup-dev" >&2
exit 127
