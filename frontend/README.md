# SENTINEL-X Frontend Control Tower

The **SENTINEL-X Control Tower** web interface built with **Next.js 16 (App Router, Turbopack)**, **React 19**, **TypeScript (`strict: true`)**, **Tailwind CSS v4**, **`@xyflow/react`**, and **`@dagrejs/dagre`**. It supports dual light/dark observability themes, real-time Redis-backed WebSocket streaming, JWT session management, and role/team-scoped views.

---

## Folder Structure

```text
frontend/
├── Dockerfile                 # Multi-stage non-root Node 20 production image
├── .dockerignore              # Excludes node_modules, .next, .git, and .env*.local from Docker builds
├── package.json               # NPM scripts and dependencies
├── package-lock.json          # Locked dependency tree
├── next.config.ts             # Next.js configuration
├── tsconfig.json              # Strict TypeScript compiler configuration
├── eslint.config.mjs          # ESLint 9 + Next.js rules
├── public/
│   └── assets/                # Centralized light/dark Sentinel-X logos and static branding images
└── src/
    ├── app/                   # Next.js App Router pages and layouts
    ├── components/            # Domain-organized reusable UI components
    ├── hooks/                 # Client React hooks (WebSocket stream, theme, responsive state)
    ├── lib/                   # Typed API client, JWT auth helpers, formatters, and utilities
    └── types/                 # TypeScript DTO interfaces mirroring backend Pydantic schemas
```

---

## Directory & Module Breakdown

### `public/assets/`
Static branding images (Sentinel-X light and dark logos). Referenced centrally through `src/lib/assets.ts` rather than scattering raw paths across components.

### `src/app/` — App Router Pages
| Route / File | Purpose |
| :--- | :--- |
| `layout.tsx`, `globals.css` | Root HTML layout, Tailwind v4 styling imports, and `AppShell` wrapper. |
| `page.tsx` (`/`) | **Fleet Overview:** Active agents, health & SLO status, filtered runs table, token/cost totals, and live WebSocket updates. |
| `runs/[runId]/page.tsx` | **Run Execution Detail:** Combines the interactive Lineage DAG, Latency Waterfall, Chronological Timeline Replay scrubber, Span Inspector drawer, Anomaly Alerts Banner, and live Cancel Run kill-switch. |
| `approvals/page.tsx` | **Governance & Approvals:** Pending HITL tool execution queue (`Approve` / `Reject` with RBAC enforcement) and append-only `audit_events` hash-chain history & verifier. |
| `costs/page.tsx` | **Cost & Token Attribution:** Run, agent, team, and model cost breakdowns plus versioned pricing rate management (`EXACT`, `ESTIMATED`, `UNKNOWN`). |
| `policies/page.tsx` | **Governance Policies:** Create, edit, and toggle hierarchical token/USD budgets, loop detection thresholds, and `auto_block_on_budget` circuit breakers. |
| `login/page.tsx` | **Authentication:** Sign-in page supporting organizational accounts, initial admin bootstrap, and one-click Demo Sandbox persona login (when enabled). |
| `settings/users/page.tsx` | **Users & Teams** *(non-demo Org Admin only)*: Create organizational teams and provision/update non-demo user roles and team scopes. |
| `settings/api-keys/page.tsx` | **API Keys** *(non-demo Org Admin only)*: Mint team-bound `sk_live_...` ingestion keys with a one-time secret reveal card and soft-revoke active keys. |
| `settings/webhooks/page.tsx` | **Outbound Webhooks** *(non-demo Org Admin only)*: Configure Slack/PagerDuty/SIEM webhook endpoints, filter subscribed event types, reveal/copy HMAC signing secrets, toggle active state, and send test pings. |

### `src/components/` — Reusable UI by Domain
- **Shell & Fleet Primitives:**
  - `AppShell.tsx`: Authentication guard (token expiration timer, focus/visibility re-checks, `/login` redirect on expired/401 sessions), responsive sidebar/header shell, and approval context provider.
  - `Sidebar.tsx`: Collapsible left navigation rail with role/sandbox-gated links and pending approval counter badge.
  - `Header.tsx`: Route title bar, theme toggle, demo Scenario Simulator trigger, WebSocket status indicator, and active user menu.
  - `StatusBadge.tsx`, `LiveConnectionBadge.tsx`, `AgentProfileModal.tsx`: Reusable status pills, WebSocket connection pill, and per-agent SLO detail modal.
- **`components/governance/`**: `ApprovalContext.tsx` (pending approval state synced via WebSockets), `ApprovalModal.tsx`, and `UserSessionMenu.tsx`.
- **`components/lineage/`**: `LineageGraph.tsx` (React Flow + Dagre auto-layout DAG), `SpanNode.tsx` (custom agent/LLM/tool node card with cost, latency, and root-cause markers), `SpanInspector.tsx` (redacted attributes, tokens, cost basis, errors), `WaterfallView.tsx`, and `RunAlertsBanner.tsx`.
- **`components/replay/`**: `TimelineReplay.tsx` (chronological execution playback scrubber).
- **`components/simulator/`**: `LaunchScenarioModal.tsx` (triggers backend demo scenarios for `demo-sandbox` users).
- **`components/ui/`**: Shared low-level UI primitives.

### `src/hooks/` — Custom Client Hooks
- `useWebSocketStream.ts`: Connects to `/ws/fleet` or `/ws/runs/{runId}` with `?token=<jwt>`, handles reconnect backoff, and dispatches incremental stream updates.
- `use-theme.ts`: Light/dark theme state synchronized with Tailwind `dark:` variants.
- `use-mobile.ts`: Responsive viewport breakpoint hook for collapsible mobile navigation.
- `use-is-client.ts`: Hydration-safe client mount detection hook.

### `src/lib/` — API Client, Auth & Utilities
- `api.ts`: Typed `apiFetch` client wrapping all backend REST calls (clears session and redirects to `/login` on `401 Unauthorized`).
- `auth.ts`: JWT storage (`localStorage`), client-side `exp` decoding (`isTokenExpired`), auth subscription store (`useSyncExternalStore`), and `verifyCurrentSession()`.
- `assets.ts`: Centralized asset paths under `/assets/...`.
- `format.ts`: Currency, token count, latency, and relative timestamp formatters (`date-fns`).
- `cn.ts` & `utils.ts`: `clsx` + `tailwind-merge` class composition helper (`cn()`).

### `src/types/` — TypeScript Contracts
- `telemetry.ts`: Strict TypeScript interfaces matching backend Pydantic v2 schemas (`CanonicalEventV1`, `RunSummaryDTO`, `SpanDTO`, `LineageGraphDTO`, `AlertDTO`, `ApprovalDTO`, `PolicyDTO`, `PricingVersionDTO`, `ApiKeyDTO`, `WebhookEndpointDTO`, etc.).

---

## Environment Variables

Only public browser-safe URLs are exposed to Next.js:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## Development & Build Commands

Run from `frontend/`:

```bash
# Install dependencies
npm install

# Start Turbopack development server (http://localhost:3000)
npm run dev

# Type-check with strict TypeScript
npx tsc --noEmit

# Run ESLint
npm run lint

# Build and start production server
npm run build
npm run start
```

