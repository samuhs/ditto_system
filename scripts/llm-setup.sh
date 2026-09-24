#!/usr/bin/env bash
# Prepares this machine to serve the LLM with Ollama on the host (GPU-backed):
# installs Ollama if missing, starts it reachable from Docker, pulls MODEL,
# smoke-tests it and registers it in the app settings.
#
# Env: MODEL (default qwen2.5:3b-instruct), OLLAMA_ID (name shown in the app),
#      YES=1 (answer yes to every prompt).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

MODEL="${MODEL:-qwen2.5:3b-instruct}"
case "$MODEL" in *:*) ;; *) MODEL="$MODEL:latest" ;; esac
OLLAMA_URL="http://localhost:11434"
SETTINGS_FILE="backend/config/app_settings.json"
OS="$(uname -s)"

reachable() { curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1; }
wait_up() {
  for _ in $(seq 1 30); do reachable && return 0; sleep 1; done
  return 1
}

step "Sistema e GPU"
has curl || fail "curl é necessário."
case "$OS" in
  Darwin)
    if [ "$(uname -m)" = "arm64" ]; then
      ok "macOS Apple Silicon: o Ollama usa a GPU via Metal"
    else
      warn "macOS Intel: o Ollama vai rodar em CPU (lento)"
    fi
    ;;
  Linux)
    grep -qi microsoft /proc/version 2>/dev/null && \
      warn "WSL detectado: fluxo não testado. Se o Docker Desktop não alcançar o Ollama, instale o Ollama no Windows."
    if has nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
      ok "GPU NVIDIA: $(nvidia-smi -L | head -1)"
    elif [ -e /dev/kfd ]; then
      ok "GPU AMD (ROCm) detectada"
    else
      warn "nenhuma GPU detectada (nvidia-smi ausente). O Ollama vai rodar em CPU, bem mais lento."
      warn "Se a máquina tem NVIDIA, instale o driver antes e rode este comando de novo."
    fi
    ;;
  *) fail "Sistema $OS não suportado. Use macOS ou Linux (no Windows, via WSL)." ;;
esac

step "Instalação do Ollama"
if has ollama; then
  ok "ollama instalado ($(ollama --version 2>/dev/null | tail -1))"
else
  warn "ollama não está instalado"
  case "$OS" in
    Darwin)
      has brew || fail "Instale o Ollama por https://ollama.com/download e rode 'make llm-setup' de novo."
      confirm "Instalar com 'brew install ollama'?" || fail "Instalação cancelada."
      brew install ollama
      ;;
    Linux)
      confirm "Instalar com o script oficial (curl -fsSL https://ollama.com/install.sh | sh, pede sudo)?" \
        || fail "Instalação cancelada. Veja https://ollama.com/download"
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
  esac
  has ollama || fail "ollama continua fora do PATH após a instalação."
  ok "ollama instalado"
fi

has_systemd_unit() {
  [ "$OS" = "Linux" ] && has systemctl && systemctl list-unit-files ollama.service >/dev/null 2>&1 \
    && systemctl list-unit-files ollama.service | grep -q '^ollama.service'
}

step "Servidor Ollama"
if reachable; then
  ok "já está rodando em $OLLAMA_URL"
else
  if has_systemd_unit; then
    echo "  iniciando o serviço systemd 'ollama' (sudo)..."
    sudo systemctl enable --now ollama
  elif [ "$OS" = "Darwin" ] && [ -d /Applications/Ollama.app ]; then
    open -a Ollama
  else
    # On Linux the container reaches the host through the Docker bridge, so bind beyond loopback.
    if [ "$OS" = "Linux" ]; then export OLLAMA_HOST=0.0.0.0:11434; fi
    nohup ollama serve >/tmp/ollama.log 2>&1 &
  fi
  wait_up || fail "o Ollama não respondeu em 30s (veja /tmp/ollama.log ou 'journalctl -u ollama')."
  ok "rodando em $OLLAMA_URL"
fi

# Linux: Ollama defaults to 127.0.0.1, which containers cannot reach via host.docker.internal.
if [ "$OS" = "Linux" ] && has ss; then
  listen=$(ss -ltnH 'sport = :11434' 2>/dev/null | awk '{print $4}')
  if [ -n "$listen" ] && ! echo "$listen" | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
    warn "o Ollama escuta só em localhost; os containers não conseguem acessá-lo."
    if has_systemd_unit && confirm "Configurar o serviço com OLLAMA_HOST=0.0.0.0 (fica acessível na rede local)?"; then
      sudo mkdir -p /etc/systemd/system/ollama.service.d
      printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' \
        | sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null
      sudo systemctl daemon-reload
      sudo systemctl restart ollama
      wait_up || fail "o Ollama não voltou após o restart."
      ok "Ollama agora escuta em 0.0.0.0:11434 (proteja a porta com firewall em redes compartilhadas)"
    else
      warn "reinicie o Ollama com OLLAMA_HOST=0.0.0.0:11434 para o Docker enxergá-lo."
    fi
  else
    ok "acessível pelos containers"
  fi
fi

step "Modelo $MODEL"
if ollama list | awk 'NR>1{print $1}' | grep -Fxq "$MODEL"; then
  ok "já baixado"
else
  echo "  baixando (pode levar alguns minutos)..."
  ollama pull "$MODEL"
  ok "baixado"
fi

step "Teste de geração"
start=$(date +%s)
reply=$(curl -sf "$OLLAMA_URL/api/generate" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Responda apenas: ok\",\"stream\":false}" \
  | sed -n 's/.*"response":"\([^"]*\)".*/\1/p') || fail "a geração falhou"
ok "resposta em $(( $(date +%s) - start ))s: ${reply:0:60}"
processor=$(ollama ps | awk -v m="$MODEL" '$1==m' | grep -oE '[0-9]+% (GPU|CPU)|[0-9]+%/[0-9]+% CPU/GPU' | head -1 || true)
case "$processor" in
  "100% GPU") ok "modelo carregado 100% na GPU" ;;
  "") warn "não consegui ler o processador em 'ollama ps'" ;;
  *) warn "modelo em '$processor': parte roda na CPU (pouca VRAM?). Considere um modelo menor." ;;
esac

step "Registro no Ditto"
if has python3; then
  msg=$(MODEL="$MODEL" OLLAMA_ID="${OLLAMA_ID:-}" SETTINGS_FILE="$SETTINGS_FILE" python3 - <<'PY'
import json, os, re
from pathlib import Path

path = Path(os.environ["SETTINGS_FILE"])
model = os.environ["MODEL"]
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
models = data.setdefault("ollama_models", [])
existing = next((m for m in models if m.get("model") == model), None)
if existing:
    print(f"já registrado como '{existing['id']}'")
else:
    mid = os.environ.get("OLLAMA_ID") or re.sub(r"[^\w-]", "-", model.removesuffix(":latest"))
    if mid in {"gemini", "ollama", "custom"} or any(m.get("id") == mid for m in models):
        mid += "-local"
    models.append({"id": mid, "model": model})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"registrado como '{mid}' (aparece como opção de LLM nos experimentos e no chat)")
PY
)
  ok "$msg"
else
  warn "python3 ausente: adicione o modelo na tela Configurações (id à sua escolha, model '$MODEL')."
fi

step "Conexão Docker → Ollama"
if [ -n "$(docker compose ps -q api 2>/dev/null)" ]; then
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5)" \
    >/dev/null 2>&1; then
    ok "o container da API alcança o Ollama"
  else
    warn "o container da API NÃO alcança o Ollama em host.docker.internal:11434"
  fi
else
  ok "API ainda não está rodando; rode 'make up' e use o modelo na aplicação"
fi
