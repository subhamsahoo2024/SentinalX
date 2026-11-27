# SENTINEL-X Python Workspace (`pybackend`)

The **`pybackend/`** directory is a Python 3.12 **`uv` workspace** containing three packages:
1. **`sdk/` (`sentinel-sdk`)** — Framework-neutral instrumentation SDK, auto-instrumentation, PII redaction, and runtime governance client.
2. **`backend/` (`sentinel-backend`)** — Async FastAPI control plane, PostgreSQL/SQLAlchemy models, Alembic migrations, Redis Pub/Sub & rate limiting, anomaly detection, cost calculation, and webhook delivery.
3. **`demo_agents/` (`sentinel-demo`)** — Reproducible multi-agent simulation scenarios, OpenTelemetry example, and zero-touch OpenAI example.

---

## Workspace Structure

```text
pybackend/
├── pyproject.toml             # uv workspace members ([sdk, backend, demo_agents]), dev tools, Ruff config
├── uv.lock                    # Locked dependency versions across all workspace packages
├── alembic.ini                # Convenience workspace Alembic configuration
├── dist/                      # Built wheel/sdist distribution artifacts
├── sdk/                       # sentinel-sdk package
├── backend/                   # sentinel-backend package
└── demo_agents/               # sentinel-demo package
```

---

## Package & Folder Breakdown

### 1. `sdk/` (`sentinel-sdk`)
Lightweight, framework-neutral instrumentation library with zero dependency on backend database models.

```text
sdk/
├── pyproject.toml             # Package metadata & runtime dependencies (pydantic, httpx, wrapt, opentelemetry-api)
├── src/sentinel_sdk/
│   ├── __init__.py            # Public SDK exports (instrument, start_run, trace_*, gate_tool, etc.)
│   ├── auto_instrument.py     # Two-line zero-code-change OpenAI (sync/async) & LangChain instrumentation via wrapt
│   ├── context.py             # contextvars-based trace_id, run_id, span hierarchy & attempt tracking (start_run)
│   ├── decorators.py          # @trace_agent, @trace_llm, @trace_tool, and synchronous HITL @gate_tool
│   ├── exporter.py            # Async/sync buffered telemetry batch exporter & flush helpers
│   ├── redactor.py            # Recursive sensitive-key & credential/PII payload redaction + truncation
│   ├── schema.py              # Canonical Event v1.0 Pydantic v2 models (CanonicalEventV1, SpanType, TokenUsage, etc.)
│   ├── exceptions.py          # Governance exceptions (RunCancelledError, BudgetCircuitBreakerError, GovernanceRejectedError, GovernanceTimeoutError)
│   ├── config.py              # .env discovery and SDK configuration loader
│   └── adapters/
│       └── langchain_cb.py    # SentinelLangChainCallback for LangChain/LangGraph chains, LLMs, and tools
└── tests/                     # Unit tests for auto-instrumentation, HITL gating, runtime control, and redaction
```

### 2. `backend/` (`sentinel-backend`)
Async FastAPI control plane backed by PostgreSQL 16 (`asyncpg`) and Redis 7.

```text
backend/
├── Dockerfile                 # Hardened two-stage non-root runtime container
├── alembic.ini                # Alembic migration configuration
├── alembic/
│   ├── env.py                 # Async SQLAlchemy migration environment
│   └── versions/              # Database schema revision history
├── pyproject.toml             # Backend dependencies (fastapi, sqlalchemy, alembic, asyncpg, redis, httpx, pyjwt, pwdlib)
├── src/sentinel_backend/
│   ├── main.py                # FastAPI app, CORS, router mounting, /health check, lifespan watchdog & retention loops
│   ├── config.py              # Pydantic Settings reading DB, Redis, JWT, anomaly thresholds, rate limits & retention
│   ├── api/                   # FastAPI HTTP routers & WebSocket handlers (no business logic)
│   │   ├── deps.py            # Ingest auth (X-API-Key / sk_live_...), JWT/dev-header ActorContext, RBAC & team scoping
│   │   ├── auth.py            # /api/auth/login, /me, /bootstrap
│   │   ├── system.py          # /api/system/config
│   │   ├── users.py           # /api/teams & /api/users CRUD (non-demo Admin)
│   │   ├── api_keys.py        # /api/api-keys CRUD & soft-revocation with SHA-256 hashing
│   │   ├── webhooks.py        # /api/webhooks CRUD & /test endpoint
│   │   ├── telemetry.py       # /api/telemetry/events & OTLP /v1/traces with atomic Redis sliding-window rate limiting
│   │   ├── agents.py          # /api/agents & /api/agents/slos (team-scoped)
│   │   ├── runs.py            # /api/runs, lineage, execution events, runtime /control-state, and /cancel kill-switch
│   │   ├── approvals.py       # /api/approvals HITL request/wait/decide & /api/audit-events hash-chain verification
│   │   ├── alerts.py          # /api/alerts listing & acknowledgement
│   │   ├── costs.py           # /api/costs/summary & versioned /api/costs/pricing
│   │   ├── policies.py        # /api/policies dynamic governance policy CRUD
│   │   ├── simulator.py       # /api/simulator demo scenario launcher
│   │   └── ws.py              # /ws/fleet & /ws/runs/{run_id} team-filtered Redis Pub/Sub WebSocket streams
│   ├── db/
│   │   └── session.py         # Async SQLAlchemy engine, async_session_maker, Base, and get_db dependency
│   ├── models/                # SQLAlchemy 2.0 ORM tables
│   │   ├── agent.py           # agents
│   │   ├── run.py             # runs
│   │   ├── span.py            # spans
│   │   ├── alert.py           # alerts
│   │   ├── approval.py        # approvals
│   │   ├── audit.py           # audit_events (append-only SHA-256 hash chain)
│   │   ├── policy.py          # policies
│   │   ├── pricing.py         # pricing_versions
│   │   ├── team.py            # teams
│   │   ├── user.py            # user_accounts
│   │   ├── api_key.py         # api_keys
│   │   └── webhook.py         # webhook_endpoints
│   ├── schemas/               # Pydantic v2 request/response DTOs
│   │   ├── telemetry.py       # CanonicalEventV1 ingest & Run/Lineage/SLO DTOs
│   │   ├── governance.py      # Approval & AuditEvent DTOs
│   │   ├── alerts.py          # AlertDTO
│   │   ├── costs.py           # CostSummaryDTO & PricingVersion DTOs
│   │   ├── policies.py        # PolicyCreate, PolicyUpdate, PolicyDTO
│   │   ├── api_keys.py        # ApiKeyCreate, ApiKeyDTO, ApiKeyCreatedDTO
│   │   ├── webhooks.py        # WebhookCreate, WebhookUpdate, WebhookDTO
│   │   └── simulator.py       # SimulatorLaunchRequest & SimulatorLaunchResponse
│   └── services/              # Core domain & background business logic
│       ├── ingestion.py       # Idempotent batch ingestion, server-side team stamping, rollups & Redis events
│       ├── otlp_mapper.py     # Maps OTLP JSON & Protobuf spans into CanonicalEventV1 with redaction
│       ├── lineage_builder.py # Constructs DAG nodes, edges, and non-double-counted cost rollups
│       ├── cost_calculator.py # Versioned pricing lookup and span/run cost status computation
│       ├── anomaly_engine.py  # LOOP_DETECTED, BUDGET_EXCEEDED, CASCADE_FAILURE, RUN_STALLED watchdog & retention purge
│       ├── governance.py      # HITL approval lifecycle, RBAC validation, audit logging & Redis wakeup
│       ├── policy_service.py  # Hierarchical policy resolution (agent -> team -> org global)
│       ├── webhooks.py        # HMAC-SHA256 signing, async delivery with backoff retries & team fan-out
│       ├── audit.py           # Append-only SHA-256 prev_hash -> entry_hash chain writer & verifier
│       ├── user_seed.py       # Seeds baseline teams, optional demo sandbox accounts, and initial admin
│       └── redis_bus.py       # Async Redis connection pool, Pub/Sub publishing & channel subscriptions
└── tests/                     # Comprehensive API, isolation, governance, cost, OTLP, webhook, and 10-scenario eval tests
```

### 3. `demo_agents/` (`sentinel-demo`)
Runnable multi-agent simulations and integration examples.

```text
demo_agents/
├── pyproject.toml             # Depends on sentinel-sdk and openai
├── src/sentinel_demo/
│   ├── agents.py              # Simulated multi-agent workflows (normal, hitl, loop, slow_loop, budget, cascade, stall)
│   ├── mock_llm.py            # Deterministic mock/live OpenAI-compatible LLM helper
│   ├── runner.py              # CLI runner (python -m sentinel_demo.runner --scenario <name>)
│   ├── otel_external_sample.py # Standard OpenTelemetry OTLP/HTTP export sample targeting /v1/traces
│   └── zero_touch_example.py  # 2-line sentinel_sdk.instrument() OpenAI example (live LLM or offline mock server)
└── tests/                     # Tests for demo scenarios, OTLP sample, and zero-touch auto-instrumentation
```

---

## Common Workspace Commands

Run from `pybackend/`:

```bash
# Sync all workspace packages and dev tools (pytest, ruff, httpx)
uv sync --all-packages --dev

# Apply database migrations
uv run --package sentinel-backend alembic -c backend/alembic.ini upgrade head

# Create a new Alembic migration after model changes
uv run --package sentinel-backend alembic -c backend/alembic.ini revision --autogenerate -m "describe_change"

# Lint all Python code (sdk, backend, demo_agents, tests)
uv run ruff check .

# Run the full test suite (all 3 packages)
uv run pytest -v

# Start FastAPI dev server
uv run --package sentinel-backend fastapi dev backend/src/sentinel_backend/main.py --port 8000

# Run zero-touch OpenAI example against a team-bound key
SENTINEL_API_KEY="sk_live_YOUR_TEAM_KEY" uv run --package sentinel-demo python -m sentinel_demo.zero_touch_example
```

