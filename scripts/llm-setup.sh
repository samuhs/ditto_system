#!/usr/bin/env bash
# Prepares this machine to serve the LLM with Ollama on the host (GPU-backed):
# installs Ollama if missing, starts it reachable from Docker, pulls MODEL,
# smoke-tests it and registers it in the app settings.
#
# Env: MODEL (default qwen2.5:3b-instruct), OLLAMA_ID (name shown in the app),
#      PARALLEL (OLLAMA_NUM_PARALLEL, default 4), YES=1 (answer yes to every prompt).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

MODEL="${MODEL:-qwen2.5:3b-instruct}"
case "$MODEL" in *:*) ;; *) MODEL="$MODEL:latest" ;; esac
OLLAMA_URL="http://localhost:11434"
PARALLEL="${PARALLEL:-4}"
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
  [ "$OS" = "Linux" ] && has systemctl && systemctl list-unit-files ollama.service 2>/dev/null | grep -q '^ollama.service'
}

# Linux: Ollama defaults to 127.0.0.1, which containers cannot reach via host.docker.internal.
serve_env() {
  if [ "$OS" = "Linux" ]; then echo "OLLAMA_HOST=0.0.0.0:11434 OLLAMA_NUM_PARALLEL=$PARALLEL"
  else echo "OLLAMA_NUM_PARALLEL=$PARALLEL"; fi
}

write_systemd_override() {
  sudo mkdir -p /etc/systemd/system/ollama.service.d
  printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\nEnvironment="OLLAMA_NUM_PARALLEL=%s"\n' "$PARALLEL" \
    | sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null
  sudo systemctl daemon-reload
}

start_detached() {
  # shellcheck disable=SC2046
  nohup env $(serve_env) ollama serve >/tmp/ollama.log 2>&1 &
}

mac_app_running() { [ "$OS" = "Darwin" ] && pgrep -f "Ollama.app/Contents/MacOS/Ollama" >/dev/null 2>&1; }

step "Servidor Ollama (OLLAMA_NUM_PARALLEL=$PARALLEL)"
override=/etc/systemd/system/ollama.service.d/override.conf
if has_systemd_unit; then
  if ! grep -q "OLLAMA_NUM_PARALLEL=$PARALLEL\"" "$override" 2>/dev/null \
    || ! grep -q 'OLLAMA_HOST=0.0.0.0' "$override" 2>/dev/null; then
    confirm "Configurar o serviço systemd com OLLAMA_HOST=0.0.0.0 (acessível na rede local) e OLLAMA_NUM_PARALLEL=$PARALLEL, reiniciando o Ollama?" \
      || fail "sem essa configuração os containers não alcançam o Ollama."
    write_systemd_override
    sudo systemctl enable ollama >/dev/null 2>&1 || true
    sudo systemctl restart ollama
  elif ! reachable; then
    sudo systemctl enable --now ollama
  fi
elif [ "$OS" = "Darwin" ] && { mac_app_running || { ! reachable && [ -d /Applications/Ollama.app ]; }; }; then
  # The macOS app reads its environment from launchctl (not persisted across reboots).
  if [ "$(launchctl getenv OLLAMA_NUM_PARALLEL)" != "$PARALLEL" ] || ! reachable; then
    if [ "$(launchctl getenv OLLAMA_NUM_PARALLEL)" = "$PARALLEL" ] || confirm "Definir OLLAMA_NUM_PARALLEL=$PARALLEL no app do Ollama e reiniciá-lo? (interrompe gerações em andamento)"; then
      launchctl setenv OLLAMA_NUM_PARALLEL "$PARALLEL"
      if mac_app_running; then
        osascript -e 'quit app "Ollama"' >/dev/null 2>&1 || true
        for _ in $(seq 1 15); do mac_app_running || break; sleep 1; done
      fi
      open -a Ollama
    else
      warn "mantido como está; o Ollama pode estar atendendo uma requisição por vez."
    fi
  fi
elif reachable; then
  if pgrep -f "ollama serve" >/dev/null 2>&1 && confirm "Reiniciar o 'ollama serve' com $(serve_env)? (interrompe gerações em andamento)"; then
    pkill -f "ollama serve" || true
    sleep 1
    start_detached
  else
    warn "servidor já rodando; confirme que ele foi iniciado com $(serve_env)."
  fi
else
  start_detached
fi
wait_up || fail "o Ollama não respondeu em 30s (veja /tmp/ollama.log ou 'journalctl -u ollama')."
ok "rodando em $OLLAMA_URL"

if [ "$OS" = "Linux" ] && has ss; then
  listen=$(ss -ltnH 'sport = :11434' 2>/dev/null | awk '{print $4}')
  if [ -n "$listen" ] && ! echo "$listen" | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
    warn "o Ollama escuta só em localhost; os containers não conseguem acessá-lo. Reinicie-o com OLLAMA_HOST=0.0.0.0:11434."
  else
    ok "acessível pelos containers (proteja a porta 11434 com firewall em redes compartilhadas)"
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
  ok "$(python3 scripts/app_models.py add "$MODEL" ${OLLAMA_ID:+"$OLLAMA_ID"})"
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
