.PHONY: setup dev health test test-rls lint validate ui-build build docker db-start db-reset db-stop

setup:
	test -f .env || cp .env.example .env
	uv sync

db-start:
	supabase start

db-reset:
	supabase db reset

db-stop:
	supabase stop

dev:
	uv run uvicorn mira_agent.main:app --reload --port 8123

health:
	curl -fsS http://localhost:8123/health
	curl -fsS http://localhost:8123/health/db

test:
	uv run pytest tests/unit tests/api

test-rls:
	RUN_RLS_TESTS=1 uv run pytest tests/integration/test_rls_real_jwt.py

lint:
	uv run python -m compileall src tests scripts
	uv run ruff check .

validate:
	uv run python -m compileall src tests scripts
	uv run ruff check .
	uv run pytest tests/unit tests/api

ui-build:
	cd ui && npm run build

build:
	cd ui && npm install && npm run build
	uv build

docker:
	docker build -t mira-agent:phase-3 .
