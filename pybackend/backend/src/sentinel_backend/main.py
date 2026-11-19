import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sentinel_backend.api import (
    agents,
    alerts,
    approvals,
    costs,
    runs,
    telemetry,
    ws,
)
from sentinel_backend.db.session import async_session_maker, engine
from sentinel_backend.services.anomaly_engine import stall_watchdog_loop
from sentinel_backend.services.cost_calculator import seed_default_pricing
from sentinel_backend.services.redis_bus import (
    close_redis,
    get_redis_client,
    get_redis_pool,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Initialize Redis connection pool
    get_redis_pool()

    # Seed default pricing versions if empty
    async with async_session_maker() as session:
        await seed_default_pricing(session)

    watchdog_task = asyncio.create_task(
        stall_watchdog_loop(async_session_maker)
    )
    try:
        yield
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
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
app.include_router(alerts.router)
app.include_router(costs.router)
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
    except Exception as e:  # noqa: BLE001
        health["postgres"] = f"error: {e}"
        health["status"] = "degraded"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Redis
    try:
        client = get_redis_client()
        await client.ping()
    except Exception as e:  # noqa: BLE001
        health["redis"] = f"error: {e}"
        health["status"] = "degraded"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(status_code=status_code, content=health)
