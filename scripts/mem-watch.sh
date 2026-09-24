#!/usr/bin/env bash
# Prints memory use every INTERVAL seconds (default 2) while you use the app:
# free memory, swap, the API's RSS and loaded embedders, and the MLX server's RSS.
# Ctrl+C stops.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

INTERVAL="${INTERVAL:-2}"
API_PORT="$(env_get API_PORT | grep . || echo 8000)"

api_json() {
  curl -sf --max-time 2 "http://localhost:$API_PORT/system/memory" 2>/dev/null \
    || curl -sf --max-time 2 "http://[::1]:$API_PORT/system/memory" 2>/dev/null
}
# "<rss>M <model@device,...>" from the /system/memory JSON on stdin
api_summary() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
models = ",".join(m["name"] + "@" + m["device"] for m in d["loaded_models"]) or "nenhum"
print(str(d["process_rss_bytes"] // 2**20) + "M", models)'
}
free_pct() {
  if has memory_pressure; then
    memory_pressure -Q 2>/dev/null | awk -F': ' '/percentage/ {print $2}'
  else
    awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {printf "%d%%\n", a*100/t}' /proc/meminfo
  fi
}
swap_used() {
  if [ "$(uname -s)" = Darwin ]; then sysctl -n vm.swapusage | awk '{print $6}'
  else free -m | awk '/Swap/ {print $3 "M"}'; fi
}
mlx_rss() {
  local pid; pid="$(pgrep -f 'mlx_lm.server' | head -1)"
  if [ -n "$pid" ]; then echo "$(( $(ps -o rss= -p "$pid") / 1024 ))M"; else echo "-"; fi
}

echo "perfil: $(memory_profile) · a cada ${INTERVAL}s · Ctrl+C para parar"
printf '%-8s %-6s %-9s %-9s %-8s %s\n' hora livre swap api_rss mlx_rss modelos
while true; do
  api="-" models="(API fora do ar)"
  body="$(api_json)"
  if [ -n "$body" ]; then
    read -r api models < <(printf '%s' "$body" | api_summary)
  fi
  printf '%-8s %-6s %-9s %-9s %-8s %s\n' "$(date +%H:%M:%S)" "$(free_pct)" "$(swap_used)" "$api" "$(mlx_rss)" "$models"
  sleep "$INTERVAL"
done
