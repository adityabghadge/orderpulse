.DEFAULT_GOAL := help
.PHONY: help setup up down reset install migrate seed seed-large bench train api test lint format web-install web web-test web-build stack stack-demo stack-down k8s-build k8s-up k8s-demo k8s-status k8s-down

VENV := backend/.venv/bin

help: ## Show available commands
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

setup: up install web-install migrate seed train ## First-time setup: services, dependencies, schema, demo data, models

up: ## Start Postgres and Redis in Docker and wait until they are ready
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

seed-large: ## Load 400,000 orders for performance testing (wipes existing data, ~1 min)
	cd backend && .venv/bin/python -m app.seed --customers 25000 --orders 400000

train: ## Train the return routing and priority models, then apply them to open returns
	cd backend && .venv/bin/python -m app.ml.train

bench: ## Measure overview latency: live queries vs materialized view vs Redis cache
	cd backend && ORDERPULSE_BACKGROUND_JOBS=false .venv/bin/python -m app.bench

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

# --- Full stack in Docker -----------------------------------------------------------------

stack: ## Run the whole app in Docker; dashboard at http://localhost:8080
	docker compose --profile app up -d --build
	@echo "Waiting for the dashboard..."
	@for i in $$(seq 1 90); do curl -sf http://localhost:8080/health >/dev/null && break; sleep 2; done
	@curl -sf http://localhost:8080/health >/dev/null && echo "Ready: http://localhost:8080" || (echo "Not ready yet; check: docker compose --profile app logs api" && exit 1)

stack-demo: ## Load demo data and train models inside the Docker stack
	docker compose --profile app run --rm --no-deps api sh -c "python -m app.seed && python -m app.ml.train"
	docker compose --profile app restart api

stack-down: ## Stop the Docker stack (data is kept)
	docker compose --profile app down

# --- Kubernetes (Docker Desktop) ----------------------------------------------------------

k8s-build: ## Build the API and dashboard images for Kubernetes
	docker build -t orderpulse-api:0.1.0 backend
	docker build -t orderpulse-web:0.1.0 frontend

k8s-up: ## Deploy to the local Kubernetes cluster; dashboard at http://localhost:8090
	kubectl apply -k infra/k8s
	kubectl -n orderpulse rollout status statefulset/postgres --timeout=180s
	kubectl -n orderpulse rollout status deployment/redis --timeout=120s
	kubectl -n orderpulse rollout status deployment/api --timeout=300s
	kubectl -n orderpulse rollout status deployment/web --timeout=120s
	@echo "Ready: http://localhost:8090"

k8s-demo: ## Load demo data and train models in the cluster, then restart the API to load them
	kubectl -n orderpulse delete job demo-data --ignore-not-found
	kubectl apply -f infra/k8s/jobs/demo-data.yaml
	kubectl -n orderpulse wait --for=condition=complete job/demo-data --timeout=900s
	kubectl -n orderpulse logs job/demo-data --tail=20
	kubectl -n orderpulse rollout restart deployment/api
	kubectl -n orderpulse rollout status deployment/api --timeout=300s

k8s-status: ## Show what's running in the cluster
	kubectl -n orderpulse get pods,services,jobs

k8s-down: ## Remove everything from the cluster (including its database)
	kubectl delete namespace orderpulse --ignore-not-found
