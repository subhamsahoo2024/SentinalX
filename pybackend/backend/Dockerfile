FROM python:3.12-slim

# Copy uv and uvx binaries from official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory to /workspace
WORKDIR /workspace

# Copy workspace configuration and dependency manifests for deterministic caching
COPY pybackend/pyproject.toml pybackend/uv.lock ./
COPY pybackend/sdk/pyproject.toml pybackend/sdk/README.md ./sdk/
COPY pybackend/backend/pyproject.toml pybackend/backend/README.md ./backend/
COPY pybackend/demo_agents/pyproject.toml pybackend/demo_agents/README.md ./demo_agents/

# Install dependencies deterministically using frozen lockfile without dev dependencies
RUN uv sync --frozen --no-dev --package sentinel-backend

# Copy source trees for SDK and Backend
COPY pybackend/sdk ./sdk
COPY pybackend/backend ./backend

# Environment variables
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run Alembic migrations on container boot followed by FastAPI production server
CMD ["sh", "-c", "uv run --no-sync --package sentinel-backend alembic -c backend/alembic.ini upgrade head && uv run --no-sync --package sentinel-backend fastapi run backend/src/sentinel_backend/main.py --host 0.0.0.0 --port 8000"]

