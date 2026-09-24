.PHONY: help up-local down-local status-local doctor certs prepare setup setup-dev llm-setup llm-up llm-down llm-status model-add model-rm model-list bench-llm up down logs test build install front-install front-test front-build ollama-up ollama-down docker-clean

# MODEL and PARALLEL are optional: each LLM server has its own defaults.

help:
	@echo "Primeira vez:"
	@echo "  make setup        checa o Docker, cria o .env e pede a chave Gemini (opcional)"
	@echo "  make up           sobe api:8000, frontend:3000, qdrant:6333, postgres:5432"
	@echo "  make llm-setup    prepara o servidor de LLM local e baixa um modelo (MODEL=..., PARALLEL=...)"
	@echo "                    Mac Apple Silicon: MLX (GPU, o mais rápido). LLM_SERVER=host usa o Ollama nativo;"
	@echo "                    LLM_SERVER=docker roda o Ollama no Docker (funciona atrás de VPN, sem GPU)"
	@echo ""
	@echo "Modelos:   make model-add <modelo> | model-rm <modelo> | model-list"
	@echo "           MLX: Qwen2.5-7B-Instruct-4bit (mlx-community) ou org/repo · Ollama: qwen3:1.7b"
	@echo "Benchmark: make bench-llm MODEL=... [LEVELS=1,2,4,8 N=16]"
	@echo ""
	@echo "Dia a dia: make down | logs | build | llm-up | llm-down | llm-status | docker-clean"
	@echo "Sem Docker p/ API e front: make up-local | down-local | status-local (só banco e Qdrant no Docker)"
	@echo "Diagnóstico de rede (VPN): make doctor"
	@echo "Dev:       make setup-dev (venv, npm, graphify, hooks) | test | front-test | front-build"

setup:
	@./scripts/setup.sh

# Development environment: backend venv, frontend packages, graphify + git hooks,
# impeccable engine. LOCAL=1 also installs the local embedders (torch).
setup-dev:
	@LOCAL="$(LOCAL)" ./scripts/setup-dev.sh

# LLM_SERVER=docker runs Ollama in a container (VPN-proof, CPU-only on macOS);
# LLM_SERVER=host goes back to the native Ollama. Omitted: keeps the last choice.
llm-setup:
	@$(if $(MODEL),MODEL="$(MODEL)") $(if $(PARALLEL),PARALLEL="$(PARALLEL)") $(if $(LLM_SERVER),LLM_SERVER="$(LLM_SERVER)") ./scripts/llm-setup.sh

# Start/stop/check whichever server llm-setup chose (make up also starts it).
llm-up:
	@./scripts/llm.sh up

llm-down:
	@./scripts/llm.sh down

llm-status:
	@./scripts/llm.sh status

# Model name: positional (make model-add qwen3:1.7b) or MODEL=... given explicitly.
ifneq ($(filter model-add model-rm,$(firstword $(MAKECMDGOALS))),)
MODEL_ARG := $(or $(word 2,$(MAKECMDGOALS)),$(if $(filter command line environment,$(origin MODEL)),$(MODEL)))
# Swallow the positional model name so make does not treat it as a target.
%:
	@:
endif

model-add:
	@./scripts/model.sh add "$(MODEL_ARG)"

model-rm:
	@./scripts/model.sh rm "$(MODEL_ARG)"

model-list:
	@./scripts/model.sh list

LEVELS ?= 1,2,4,8
N ?= 16
BASE_URL ?= $(shell ./scripts/llm.sh url 2>/dev/null)
bench-llm:
	@[ -n "$(MODEL)" ] || { echo "informe o modelo: make bench-llm MODEL=... (veja make model-list)"; exit 1; }
	@python3 scripts/bench_llm.py --base-url "$(BASE_URL)" --model "$(MODEL)" --levels "$(LEVELS)" -n "$(N)"

# Exports the host's trusted CAs for the Docker builds (VPN/proxy-safe builds).
certs:
	@./scripts/host-certs.sh

# Builds on the host what the images would download (frontend dist, torch wheel),
# for networks that block the containers' egress. Best-effort: anything it
# cannot do is left to the Docker build. SKIP_HOST_BUILD=1 turns it off.
prepare: certs
	@./scripts/prepare-artifacts.sh

build: prepare
	docker compose build

# --build picks up code and the freshly built frontend; unchanged layers are cached.
up: prepare
	@./scripts/local.sh stop-apps
	@./scripts/check-ports.sh
	docker compose up -d --build
	@./scripts/llm.sh up || true

down:
	docker compose down

# Alternative to `make up`: API and frontend run on the host (backend/.venv,
# Vite), only Postgres and Qdrant in Docker, every local hop over IPv6
# loopback. For machines whose VPN breaks 127.0.0.1 or where Docker cannot
# reach a host LLM server. Needs `make setup-dev` once.
up-local:
	@./scripts/local.sh up

down-local:
	@./scripts/local.sh down

status-local:
	@./scripts/local.sh status

# Tests every network hop the app relies on and says which one fails.
doctor:
	@./scripts/doctor.sh

logs:
	docker compose logs -f

# Frees build cache and dangling images left by rebuilds. Never touches volumes (data).
docker-clean:
	docker builder prune -f
	docker image prune -f
	docker system df

# The backend venv (made by setup-dev) when present, else the python on PATH.
BACKEND_PY = $(if $(wildcard backend/.venv/bin/python),.venv/bin/python,python)

install:
	cd backend && $(BACKEND_PY) -m pip install -e ".[dev]"

test:
	cd backend && $(BACKEND_PY) -m pytest -v

front-install:
	cd frontend && npm install

front-test:
	cd frontend && npm run test -- --run

front-build:
	@[ -d frontend/node_modules ] || (cd frontend && npm ci)
	cd frontend && npm run build

# Legacy names for llm-up / llm-down.
ollama-up: llm-up

ollama-down: llm-down
