.DEFAULT_GOAL := help
.PHONY: help setup up down reset install migrate seed api test lint format web-install web web-test web-build

VENV := backend/.venv/bin

help: ## Show available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: up install web-install migrate seed ## First-time setup: database, dependencies, schema, demo data

up: ## Start Postgres in Docker and wait until it is ready
	docker compose up -d --wait

down: ## Stop the containers (data is kept)
	docker compose down

reset: ## Stop the containers and delete all database data
	docker compose down -v

install: ## Create the Python virtual environment and install dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ".[dev]"

migrate: ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

seed: ## Load demo data (wipes existing data)
	cd backend && .venv/bin/python -m app.seed

api: ## Run the API with auto-reload at http://localhost:8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app

test: ## Run the test suite
	cd backend && .venv/bin/pytest

lint: ## Check code style
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .

format: ## Auto-format the code
	cd backend && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

web-install: ## Install frontend dependencies
	cd frontend && npm install --no-fund --no-audit

web: ## Run the dashboard at http://localhost:5173 (needs `make api` running)
	cd frontend && npm run dev

web-test: ## Type-check and test the frontend
	cd frontend && npm run typecheck && npm test

web-build: ## Build the dashboard for production
	cd frontend && npm run build
