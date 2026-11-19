from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sentinel_backend.api import agents, approvals, runs, telemetry, ws
from sentinel_backend.db.session import async_session_maker, engine
from sentinel_backend.services.redis_bus import (
    close_redis,
    get_redis_client,
    get_redis_pool,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Initialize Redis connection pool
    get_redis_pool()
    yield
    # Gracefully shut down Redis connection pool and DB engine
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Sentinel Backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure unhandled 500 exceptions still return CORS headers to frontend."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )

# Mount Routers
app.include_router(telemetry.router)
app.include_router(agents.router)
app.include_router(runs.router)
app.include_router(approvals.router)
app.include_router(ws.router)


@app.get("/health", tags=["system"])
async def health_check() -> JSONResponse:
    """Health check endpoint verifying both PostgreSQL and Redis connectivity."""
    health: dict[str, str] = {
        "status": "ok",
        "postgres": "ok",
        "redis": "ok",
    }
    status_code = status.HTTP_200_OK

    # Check PostgreSQL
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        health["postgres"] = f"error: {e}"
        health["status"] = "degraded"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Redis
    try:
        client = get_redis_client()
        await client.ping()
    except Exception as e:
        health["redis"] = f"error: {e}"
        health["status"] = "degraded"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(status_code=status_code, content=health)
