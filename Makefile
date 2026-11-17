.PHONY: help infra-up infra-down migrate backend-dev frontend-dev test

help:
	@echo "Available commands:"
	@echo "  make infra-up     - Start PostgreSQL and Redis infrastructure containers"
	@echo "  make infra-down   - Stop infrastructure containers"
	@echo "  make migrate      - Run database migrations"
	@echo "  make backend-dev  - Run FastAPI backend development server"
	@echo "  make frontend-dev - Run Next.js frontend development server"
	@echo "  make test         - Run test suite"

infra-up:
	docker compose up -d

infra-down:
	docker compose down

migrate:
	uv run --package sentinel-backend alembic upgrade head

backend-dev:
	uv run --package sentinel-backend fastapi dev backend/src/sentinel_backend/main.py

frontend-dev:
	cd frontend && npm run dev

test:
	uv run pytest

