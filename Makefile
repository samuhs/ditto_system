.PHONY: help setup llm-setup model-add model-rm model-list bench-llm up down logs test build install front-install front-test front-build ollama-up ollama-down docker-clean

MODEL ?= qwen2.5:3b-instruct
PARALLEL ?= 4

help:
	@echo "Primeira vez:"
	@echo "  make setup        checa o Docker, cria o .env e pede a chave Gemini (opcional)"
	@echo "  make up           sobe api:8000, frontend:3000, qdrant:6333, postgres:5432"
	@echo "  make llm-setup    prepara o Ollama (GPU, PARALLEL=4) e baixa o modelo; MODEL=... para trocar"
	@echo ""
	@echo "Modelos:   make model-add qwen3:1.7b | model-rm qwen3:1.7b | model-list"
	@echo "Benchmark: make bench-llm MODEL=... [LEVELS=1,2,4,8 N=16]"
	@echo ""
	@echo "Dia a dia: make down | logs | build | ollama-up | ollama-down | docker-clean"
	@echo "Dev:       make install | test | front-install | front-test | front-build"

setup:
	@./scripts/setup.sh

llm-setup:
	@MODEL="$(MODEL)" PARALLEL="$(PARALLEL)" ./scripts/llm-setup.sh

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
BASE_URL ?= http://localhost:11434/v1
bench-llm:
	@python3 scripts/bench_llm.py --base-url "$(BASE_URL)" --model "$(MODEL)" --levels "$(LEVELS)" -n "$(N)"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# Frees build cache and dangling images left by rebuilds. Never touches volumes (data).
docker-clean:
	docker builder prune -f
	docker image prune -f
	docker system df

install:
	cd backend && pip install -e ".[dev]"

test:
	cd backend && python -m pytest -v

front-install:
	cd frontend && npm install

front-test:
	cd frontend && npm run test -- --run

front-build:
	cd frontend && npm run build

ollama-up:
	@if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then \
		echo "ollama ja esta rodando"; \
	else \
		echo "iniciando ollama serve..."; \
		export OLLAMA_NUM_PARALLEL=$(PARALLEL); \
		if [ "$$(uname -s)" = Linux ]; then export OLLAMA_HOST=0.0.0.0:11434; fi; \
		nohup ollama serve >/tmp/ollama.log 2>&1 & \
		until curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 1; done; \
		echo "ollama pronto"; \
	fi; \
	ollama list

ollama-down:
	@pkill -f "ollama serve" && echo "ollama parado" || echo "nenhum processo 'ollama serve' rodando"
