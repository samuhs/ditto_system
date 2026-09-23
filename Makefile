.PHONY: up down logs test build install ollama-up ollama-down docker-clean

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
		nohup ollama serve >/tmp/ollama.log 2>&1 & \
		until curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 1; done; \
		echo "ollama pronto"; \
	fi; \
	ollama list

ollama-down:
	@pkill -f "ollama serve" && echo "ollama parado" || echo "nenhum processo 'ollama serve' rodando"
