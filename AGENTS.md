You are an expert full-stack AI systems engineer helping me build
SENTINEL-X.
Write clean, simple, maintainable code. Prioritize clarity over
unnecessary abstraction.
Think like a senior distributed systems and frontend architect.
---
## Project Overview
We are building SENTINEL-X, a framework-neutral observability and
runtime-governance control tower for multi-agent AI systems.
The platform includes:
- Unified telemetry ingestion converting agent, LLM, and tool events into a versioned Canonical Event v1.0 schema
- Fleet Overview dashboard showing active agents, health status, runs, tokens, and spend
- Real-time interactive Agent Lineage DAG built with React Flow and Dagre
- Synchronous Human-in-the-Loop (HITL) pre-execution approval gate with RBAC and append-only audit logs
- Deterministic causal anomaly detection (repeated tool loops, token/cost budget overruns, stalled runs, and upstream root-cause tracing)
- Versioned cost attribution without double-counting and chronological execution replay
Keep the implementation simple and readable.
---
## Tech Stack
- Python 3.12 with `uv` workspace (`sdk`, `backend`, `demo_agents`)
- FastAPI (async REST API and WebSockets)
- PostgreSQL 16 with SQLAlchemy 2.0 (asyncpg) and Alembic
- Redis 7 (Pub/Sub for live WebSocket streaming and HITL approval wakeup)
- Pydantic v2 and OpenTelemetry API
- Next.js 15 (App Router) and TypeScript
- Tailwind CSS
- `@xyflow/react` and `@dagrejs/dagre`
- `lucide-react` and `date-fns`
Do not introduce new major libraries unless there is a strong reason.
Ask before installing anything new.
---
## Development Philosophy
Build feature by feature.
For every feature:
1. Read this file first.

2. Keep the implementation simple.

3. Avoid overengineering.

4. Prefer readable code over clever code.

5. Build the smallest useful version first.

6. Refactor only when repetition appears.
---
## Decision Making
If something is unclear or could be improved, suggest a better
approach. If a new library would significantly help, recommend it,
explain why, and ask before adding it.
Do not install new libraries without approval.
---
## Architecture
Use this folder structure:

```

sentinal-x/
├── docker-compose.yml
├── .env
├── Makefile
├── pybackend/
│   ├── pyproject.toml
│   ├── sdk/
│   │   └── src/sentinel_sdk/
│   ├── backend/
│   │   ├── alembic/
│   │   └── src/sentinel_backend/
│   │       ├── api/
│   │       ├── db/
│   │       ├── models/
│   │       ├── schemas/
│   │       └── services/
│   └── demo_agents/
│       └── src/sentinel_demo/
└── frontend/
└── src/
├── app/
│   ├── approvals/
│   ├── costs/
│   └── runs/[runId]/
├── components/
│   ├── governance/
│   ├── lineage/
│   └── replay/
├── hooks/
├── lib/
└── types/

```
**pybackend/sdk/** is for framework-neutral instrumentation decorators, context propagation, PII redaction, and the Canonical Event v1.0 schema. Keep it lightweight and independent of backend database models.
**pybackend/backend/src/sentinel_backend/api/** is for FastAPI route handlers and WebSocket endpoints only. Keep business logic in **services/**.
**pybackend/backend/src/sentinel_backend/services/** is for core domain logic (telemetry ingestion, lineage DAG construction, anomaly and root-cause evaluation, cost calculation, and Redis Pub/Sub).
**pybackend/demo_agents/** is for reproducible multi-agent test scenarios (normal delegation, tool loops, budget overruns, cascading failures, and HITL gates).
**frontend/src/app/** is for Next.js App Router pages and layouts only. Pages compose components and call hooks or API helpers. They should not contain large reusable UI blocks or graph layout logic.
**frontend/src/components/** is for reusable UI grouped by domain. Create a component when it is reused in multiple places, when it makes a page easier to read, or when it represents a clear UI concept. Examples for this app: `LineageGraph`, `SpanNode`, `SpanInspector`, `ApprovalModal`, `TimelineReplay`. Do not create components too early.
**frontend/src/hooks/** is for reusable client hooks such as `useWebSocketStream`.
**frontend/src/lib/** is for typed API clients and utility helpers (`api.ts`, `cn.ts`). Never expose secret keys here.
**frontend/src/types/** is for TypeScript interfaces mirroring backend Pydantic DTOs and Canonical Event v1.0.
---
## UI Rules
For any UI task:
- Replicate the provided design or dark-mode observability aesthetic consistently.
- Match layout, spacing, padding, font sizes, font hierarchy, colors,
border radius, shadows, alignment, and proportions.

- Do not approximate. Do not simplify unless explicitly asked.
---
## Styling Rules
Use Tailwind CSS utility classes. Do not write custom CSS files unless it is not possible to style with Tailwind classes.
Use the Tailwind CSS version installed in `frontend/package.json`. Do not upgrade without approval.
Reuse class patterns through `cn()` (`clsx` + `tailwind-merge`) in `frontend/src/lib/cn.ts`.
### Style Exception List
Use inline `style` props or scoped CSS only for:
- React Flow (`@xyflow/react`) node coordinates, handle positioning, and dynamic edge stroke animations
- Dynamic dimensions or progress percentages calculated at runtime
- Keyframe animations not covered by default Tailwind utilities
Everywhere else, use Tailwind CSS classes.
---
## Asset & Icon Rule
Use centralized icons and static assets.
1. Use `lucide-react` for all UI icons rather than inline raw `<svg>` tags.

2. If static images or badges are added, centralize imports in `frontend/src/lib/assets.ts` and reference them from that object.

3. Do not scatter raw asset paths across pages or components.
---
## State Management
- PostgreSQL and Redis are the single source of truth for runs, spans, alerts, costs, and approvals.
- React local state (`useState`, `useReducer`) for UI filters, selected nodes, drawer visibility, and replay scrubber position.
- WebSocket stream hook (`useWebSocketStream`) for live incremental updates from FastAPI.
- Do not add Redux, Zustand, or extra client state libraries without approval.
---
## TypeScript & Python Typing
- TypeScript strict mode enabled (`"strict": true`).
- No `any` in TypeScript; use explicit interfaces or `unknown` with type guards.
- Keep types simple, readable, and aligned with `CanonicalEventV1`.
- Use full Python 3.12 type annotations and Pydantic v2 models across `sdk`, `backend`, and `demo_agents`.
---
## Feature Implementation
When building a feature:
1. Read this file first.

2. Identify the files to change.

3. Keep changes focused.

4. Do not rewrite unrelated code.

5. Follow existing patterns.

6. Make sure the feature works end to end.

7. Fix lint (`ruff`, `eslint`) and type errors (`tsc --noEmit`) before finishing.
---
## Secrets
- Never expose secret keys in `frontend/` client code.
- Only expose `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` to the browser.
- Store `SENTINEL_API_KEY`, `DATABASE_URL`, `REDIS_URL`, and any LLM provider keys in `.env` and read them only in `pybackend/`.
- Redact sensitive keys (`token`, `secret`, `password`, `api_key`, `authorization`) inside `sentinel_sdk` before emitting telemetry.
---
## Authentication & Authorization
- Protect telemetry ingestion (`POST /api/telemetry/events`) with `X-API-Key` validation against `SENTINEL_API_KEY`.
- Enforce Role-Based Access Control (`viewer`, `operator`, `approver`, `admin`) on the FastAPI backend for human-in-the-loop approval decisions and policy mutations.
- Record every approval and governance action in the append-only `audit_events` table.
---
## Communication
Be concise. Explain what changed and how to test it.
---
## Final Reminder
Before every feature:
- Read this file.

- Follow it strictly.

- Build clean, simple code.

- Replicate UI exactly when designs are provided.
