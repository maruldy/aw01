UV=uv
NPM=npm --prefix apps/web

.PHONY: setup setup-web test lint run-api run-web backfill

setup:
	$(UV) sync --extra dev

setup-web:
	$(NPM) install

test:
	$(UV) run --extra dev pytest

lint:
	$(UV) run --extra dev ruff check src tests

run-api:
	$(UV) run uvicorn work_harness.main:app --reload --host 0.0.0.0 --port 8000

run-web:
	$(NPM) run dev -- --host 0.0.0.0 --port 5173

backfill:
	curl -X POST http://localhost:8000/backfill/trigger
