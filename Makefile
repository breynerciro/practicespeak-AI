.PHONY: run dev test lint format typecheck docker up down clean

run:        ## start via run.sh (Ollama + app + QR)
	./run.sh start

dev:        ## uvicorn with autoreload
	.venv/bin/uvicorn backend.main:app --reload --port $${NOVA_PORT:-8000}

test:       ## pytest with coverage gate
	.venv/bin/pytest

lint:       ## ruff + mypy
	.venv/bin/ruff check backend
	.venv/bin/mypy backend

format:     ## ruff autofix
	.venv/bin/ruff check --fix backend

docker:     ## build image
	docker compose build

up:         ## docker compose up
	docker compose up -d

down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage **/__pycache__
