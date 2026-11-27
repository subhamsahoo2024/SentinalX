# Stage 1: Dependency resolution & non-editable wheel build
FROM python:3.12-slim AS builder

# Copy uv binary from official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace/pybackend

# Copy workspace manifests first for deterministic dependency layer caching
COPY pybackend/pyproject.toml pybackend/uv.lock ./
COPY pybackend/sdk/pyproject.toml pybackend/sdk/README.md ./sdk/
COPY pybackend/backend/pyproject.toml pybackend/backend/README.md ./backend/
COPY pybackend/demo_agents/pyproject.toml pybackend/demo_agents/README.md ./demo_agents/

# Install third-party dependencies only
RUN uv sync --frozen --no-dev --no-install-project --no-install-workspace --package sentinel-backend --package sentinel-demo

# Copy internal workspace packages and install non-editably
COPY pybackend/sdk ./sdk
COPY pybackend/backend ./backend
COPY pybackend/demo_agents ./demo_agents

RUN uv sync --frozen --no-dev --no-editable --package sentinel-backend --package sentinel-demo

# Stage 2: Minimal non-root runtime image
FROM python:3.12-slim AS runtime

RUN groupadd -r sentinel && \
    useradd -r -g sentinel -d /app -s /sbin/nologin sentinel

WORKDIR /app

COPY --from=builder --chown=sentinel:sentinel /workspace/pybackend/.venv /app/.venv
COPY --from=builder --chown=sentinel:sentinel /workspace/pybackend/backend/alembic.ini /app/backend/alembic.ini
COPY --from=builder --chown=sentinel:sentinel /workspace/pybackend/backend/alembic /app/backend/alembic
COPY --from=builder --chown=sentinel:sentinel /workspace/pybackend/backend/src /app/backend/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER sentinel

EXPOSE 8000

CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && fastapi run backend/src/sentinel_backend/main.py --host 0.0.0.0 --port 8000"]
