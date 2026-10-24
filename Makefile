# Autonomous QA Swarm — developer commands. Plain POSIX-friendly; works from Git Bash / WSL.
# PowerShell equivalents are documented in README.md.

UV ?= uv
NPM ?= npm
COMPOSE ?= docker compose

.PHONY: setup up down logs migrate migration seed dev dev-api dev-api-reload dev-web scheduler exec-host lint typecheck test test-unit test-integration check fmt build audit migrate-roundtrip

setup:
	cd backend && $(UV) sync --all-groups
	cd web && $(NPM) ci

up:
	$(COMPOSE) up -d postgres
	$(COMPOSE) up -d --build api web

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api web

migrate:
	cd backend && $(UV) run alembic upgrade head

migration:
	cd backend && $(UV) run alembic revision --autogenerate -m "$(m)"

seed:
	cd backend && $(UV) run python -m qaswarm.db.seed

dev-api:
	cd backend && $(UV) run python -m qaswarm.api.serve --port 8000

dev-api-reload:
	cd backend && $(UV) run uvicorn qaswarm.api.app:create_app --factory --reload --port 8000

scheduler:
	cd backend && $(UV) run python -m qaswarm.workflow.scheduler

exec-host:
	cd backend && $(UV) run python -m qaswarm_exec

dev-web:
	cd web && $(NPM) run dev

dev:
	@echo "Run 'make dev-api' and 'make dev-web' in two terminals (or 'make up' for Compose)."

lint:
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check .
	cd web && $(NPM) run lint && $(NPM) run format:check

typecheck:
	cd backend && $(UV) run python -m mypy
	cd web && $(NPM) run typecheck

test-unit:
	cd backend && $(UV) run python -m pytest tests/unit -q

test-integration:
	cd backend && $(UV) run python -m pytest tests/integration -q

test:
	cd backend && $(UV) run python -m pytest -q
	cd web && $(NPM) test -- --run

build:
	cd web && $(NPM) run build

check: lint typecheck test build

audit:
	cd backend && $(UV) run --with pip-audit python -m pip_audit --skip-editable
	cd web && $(NPM) audit

migrate-roundtrip:
	cd backend && $(UV) run alembic upgrade head && $(UV) run alembic downgrade base && $(UV) run alembic upgrade head

fmt:
	cd backend && $(UV) run ruff check --fix . && $(UV) run ruff format .
	cd web && $(NPM) run format
