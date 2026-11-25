# SENTINEL-X

> **Framework-neutral observability and runtime-governance control tower for multi-agent AI systems.**

SENTINEL-X delivers unified real-time execution telemetry, interactive lineage directed acyclic graphs (DAGs), deterministic causal anomaly detection, versioned cost attribution without double-counting, chronological execution replay, and synchronous human-in-the-loop (HITL) pre-execution governance gates with role-based access control (RBAC).

---

## Architecture Overview: Dual-Plane Control Tower

SENTINEL-X is architected with two distinct, decoupled operational planes:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               SENTINEL-X CONTROL TOWER                                 │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│  1. Asynchronous Telemetry Plane         │  2. Synchronous Governance (HITL) Plane     │
│  (Non-blocking Observability)            │  (Pre-Execution Enforcement Gate)           │
├──────────────────────────────────────────┼─────────────────────────────────────────────┤
│ • Framework-neutral decorators:          │ • High-risk tool barrier:                   │
│   @trace_agent, @trace_tool,             │   @gate_tool(risk_level, policy_reason)     │
│   mock_llm_completion, start_run         │                                             │
│ • Local in-memory buffering & auto PII   │ • Synchronous workflow block:               │
│   redaction (keys, tokens, secrets)      │   Enters AWAITING_APPROVAL status           │
│ • Idempotent batch event ingestion:      │ • Instant wakeup via Redis Pub/Sub channel: │
│   POST /api/telemetry/events             │   approval:{approval_id}:decision           │
│ • Redis Pub/Sub live streaming:          │ • RBAC authorization on decisions:          │
│   fleet:stream & run:{runId}:stream      │   approver / admin roles only               │
│ • Real-time Lineage DAG & Anomaly Engine │ • Append-only immutable audit trail:        │
│   (loops, budgets, stalls, cascades)     │   audit_events table                        │
└──────────────────────────────────────────┴─────────────────────────────────────────────┘
```

### 1. Asynchronous Telemetry Ingestion Plane
- **Zero-Friction Instrumentation**: Lightweight `@trace_agent` and `@trace_tool` decorators instrument arbitrary Python multi-agent workflows without coupling to specific agent frameworks (LangChain, AutoGen, CrewAI, or custom loops).
- **Client-Side PII Redaction**: Sensitive attributes matching credential patterns (`token`, `secret`, `password`, `api_key`, `authorization`) are automatically masked at the SDK layer before leaving the runtime environment.
- **Canonical Event Schema v1.0**: Standardized schema across `AGENT`, `LLM`, `TOOL`, and `APPROVAL` spans.
- **Deterministic Anomaly Engine**:
  - **Repeated Tool Loops (`LOOP_DETECTED`)**: Flags 3+ identical tool signatures executed within a sliding time window (default 30s).
  - **Token Budget Overruns (`BUDGET_EXCEEDED`)**: Identifies cumulative token consumption exceeding thresholds (default 5,000 tokens) and pinpoints highest-consumption spans.
  - **Cascading Failures (`CASCADE_FAILURE`)**: Traces multi-tier error propagation back to the root-cause origin span.
  - **Stalled Runs (`RUN_STALLED`)**: Watchdog monitors active runs and transitions silent workflows to `STALLED` after timeout thresholds (default 25s).
- **Versioned Cost Attribution**: Leaf-level token pricing with provider versions, preventing double-counting on parent agent wrappers, with explicit tracking of missing/unmetered token spans.

### 2. Synchronous Human-in-the-Loop (HITL) Control Plane
- **Pre-Execution Barrier**: High-risk operations decorated with `@gate_tool` pause execution before side effects take place.
- **Synchronous Redis Wakeup**: The SDK issues an approval request (`POST /api/approvals/request`) and suspends execution on a long-polling wakeup listener (`GET /api/approvals/{id}/wait`) subscribing to `approval:{id}:decision`.
- **Role-Based Access Control (RBAC)**: Operator/viewer roles receive `403 Forbidden` on governance decisions; only authorized `approver` and `admin` actors can approve or reject actions.
- **Append-Only Audit Log**: Every governance decision is recorded in the immutable `audit_events` table with actor context, timestamp, and rationale.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI (Async REST + WebSockets), SQLAlchemy 2.0 (asyncpg), Alembic, Pydantic v2, OpenTelemetry API, `uv` Workspace.
- **Storage & Streaming**: PostgreSQL 16 (relational telemetry & audit logs), Redis 7 (live WebSocket streaming & HITL wakeup).
- **Frontend**: Next.js 15 (App Router), TypeScript (strict mode), Tailwind CSS, `@xyflow/react` + `@dagrejs/dagre` (Lineage DAG), `lucide-react`, `date-fns`.

---

## Quickstart

### Option A: Full-Stack Docker Deployment (Recommended)

Start the entire Sentinel platform (PostgreSQL, Redis, FastAPI Backend, and Next.js Frontend) with a single command:

```bash
docker compose up --build
```

- **Frontend Console**: [http://localhost:3000](http://localhost:3000)
  - Fleet Overview & KPI Dashboard: `/`
  - Interactive Lineage DAG & Execution Replay: `/runs/[runId]`
  - Human-in-the-Loop Governance Queue: `/approvals`
  - Versioned Cost Attribution & Rate Editor: `/costs`
- **FastAPI OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL**: `localhost:5432` (`sentinel` / `sentinel_dev` / `sentinel_x`)
- **Redis**: `localhost:6379`

To shut down containers and volumes:
```bash
docker compose down -v
```

---

### Option B: Local Development Mode (`uv` + `npm`)

#### 1. Start Infrastructure
```bash
# Start PostgreSQL and Redis containers with healthchecks
docker compose up -d postgres redis
```

#### 2. Backend Setup & Migrations
```bash
# Navigate to the Python workspace
cd pybackend

# Sync all workspace dependencies
uv sync

# Run database migrations
uv run --package sentinel-backend alembic -c backend/alembic.ini upgrade head

# Start FastAPI development server on port 8000
uv run --package sentinel-backend fastapi dev backend/src/sentinel_backend/main.py --port 8000
```

#### 3. Frontend Setup
```bash
# In a separate terminal, navigate to the frontend directory
cd frontend

# Install dependencies
npm ci

# Start Next.js development server on port 3000
npm run dev
```

---

## Reproducible Multi-Agent Demo Scenarios

SENTINEL-X includes an IT Incident Triage multi-agent demo (`sentinel-demo`) reproducing real-world enterprise operational conditions.

Run each scenario using `uv` from the repository root or `pybackend/` directory:

### 1. Normal Multi-Agent Delegation
Coordinator delegates to diagnostic and remediation agents; workflow completes cleanly with status `SUCCEEDED`.
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario normal
```

### 2. Human-in-the-Loop (HITL) Governance Gate
Triggers a high-risk `@gate_tool` action (`restart_production_cluster`). Workflow transitions to `AWAITING_APPROVAL` and pauses until an authorized approver decides the request in the web console at [http://localhost:3000/approvals](http://localhost:3000/approvals).
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario hitl
```

### 3. Repeated Tool Loop (`LOOP_DETECTED`)
Diagnostic agent executes 4 consecutive queries against a flaky endpoint with identical parameters, triggering a `LOOP_DETECTED` anomaly alert while preserving acyclic attempt nodes in the Lineage DAG.
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario loop
```

### 4. Token Budget Overrun (`BUDGET_EXCEEDED`)
Verbose analysis agent generates ~7,500 tokens across multiple inference calls, breaching the configured token budget threshold (`RUN_TOKEN_BUDGET=5000`) and pinpointing the culprit LLM span.
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario budget
```

### 5. Cascading Failure Chain (`CASCADE_FAILURE`)
Corrupt schema fetch tool throws an unhandled `ValueError`, propagating downstream to trigger diagnostic and coordinator agent failures. Sentinel attributes `is_root_cause=True` to the upstream origin tool.
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario cascade
```

### 6. Stalled Run Watchdog (`RUN_STALLED`)
Agent starts and emits an initial `RUNNING` telemetry span before encountering silent execution hang. Sentinel's background watchdog identifies the stall after 25s, sets terminal status `STALLED`, and alerts operators.
```bash
cd pybackend
uv run --package sentinel-demo python -m sentinel_demo.runner --scenario stall
```

#### Optional CLI Flags
All demo scenarios support customization:
```bash
uv run --package sentinel-demo python -m sentinel_demo.runner \
  --scenario normal \
  --ticket-id "INC-9901" \
  --team "sec-ops" \
  --description "High latency detected on core auth gateway" \
  --dashboard-host "http://localhost:3000"
```

---

## Automated Evaluation & Test Suite

The test suite validates domain services, REST routes, WebSocket streaming, and all 10 core evaluation scenarios:

```bash
# Run all 68 backend tests (Lineage, Anomaly Engine, Governance, Costs, Evaluation)
cd pybackend
uv run pytest

# Run the 10-scenario automated evaluation suite specifically
uv run pytest backend/tests/test_evaluation_suite.py -v

# Run code formatting and lint checks
uv run ruff check
```

Frontend verification:
```bash
cd frontend
npm run lint
npm run build
```

---

## Repository Structure

```
sentinal-x/
├── docker-compose.yml          # Full-stack composition (Postgres, Redis, Backend, Frontend)
├── .env                        # Central environment configuration
├── Makefile                    # Developer shortcut targets
├── pybackend/                  # Python 3.12 uv workspace
│   ├── pyproject.toml          # Workspace root configuration
│   ├── sdk/                    # Non-blocking telemetry SDK & Canonical Event schema
│   │   └── src/sentinel_sdk/
│   ├── backend/                # FastAPI control tower & persistence layer
│   │   ├── Dockerfile          # Container packaging for backend service
│   │   ├── alembic/            # Database schema migrations
│   │   └── src/sentinel_backend/
│   │       ├── api/            # REST and WebSocket route handlers
│   │       ├── db/             # SQLAlchemy asyncpg session setup
│   │       ├── models/         # Postgres database models
│   │       ├── schemas/        # Pydantic v2 DTOs
│   │       └── services/       # Domain services (ingestion, lineage, costs, anomalies)
│   └── demo_agents/            # Reproducible multi-agent scenario test harness
│       └── src/sentinel_demo/
└── frontend/                   # Next.js 15 App Router web console
    ├── Dockerfile              # Multi-stage production container build
    └── src/
        ├── app/                # Next.js App Router routes (/runs/[runId], /approvals, /costs)
        ├── components/         # Reusable UI domain components (DAG, Replay, Governance)
        ├── hooks/              # Custom React hooks (useWebSocketStream)
        ├── lib/                # Typed API client and styling utilities
        └── types/              # TypeScript interfaces mirroring Canonical Event v1.0
```

---

