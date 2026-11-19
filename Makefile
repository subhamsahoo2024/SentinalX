.PHONY: help docker-up docker-down infra-up infra-down migrate backend-dev frontend-dev test eval demo-normal demo-hitl demo-loop demo-budget demo-cascade demo-stall

help:
	@echo "SENTINEL-X Developer Commands:"
	@echo "  make docker-up    - Build and start full stack in Docker (Postgres, Redis, Backend, Frontend)"
	@echo "  make docker-down  - Stop all Docker containers"
	@echo "  make infra-up     - Start only PostgreSQL and Redis containers"
	@echo "  make infra-down   - Stop infrastructure containers"
	@echo "  make migrate      - Run database migrations"
	@echo "  make backend-dev  - Run FastAPI backend development server"
	@echo "  make frontend-dev - Run Next.js frontend development server"
	@echo "  make test         - Run full pytest test suite"
	@echo "  make eval         - Run 10-scenario evaluation suite"
	@echo "  make demo-normal  - Run Normal Multi-Agent Delegation demo"
	@echo "  make demo-hitl    - Run Human-in-the-Loop Governance Gate demo"
	@echo "  make demo-loop    - Run Repeated Tool Loop Anomaly demo"
	@echo "  make demo-budget  - Run Token Budget Overrun Anomaly demo"
	@echo "  make demo-cascade - Run Cascading Failure Chain demo"
	@echo "  make demo-stall   - Run Stalled Run Watchdog demo"

docker-up:
	docker compose up --build

docker-down:
	docker compose down

infra-up:
	docker compose up -d postgres redis

infra-down:
	docker compose down

migrate:
	cd pybackend && uv run --package sentinel-backend alembic -c backend/alembic.ini upgrade head

backend-dev:
	cd pybackend && uv run --package sentinel-backend fastapi dev backend/src/sentinel_backend/main.py --port 8000

frontend-dev:
	cd frontend && npm run dev

test:
	cd pybackend && uv run pytest

eval:
	cd pybackend && uv run pytest backend/tests/test_evaluation_suite.py -v

demo-normal:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario normal

demo-hitl:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario hitl

demo-loop:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario loop

demo-budget:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario budget

demo-cascade:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario cascade

demo-stall:
	cd pybackend && uv run --package sentinel-demo python -m sentinel_demo.runner --scenario stall
