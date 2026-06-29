.PHONY: up down logs test build install

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

install:
	cd backend && pip install -e ".[dev]"

test:
	cd backend && python -m pytest -v
