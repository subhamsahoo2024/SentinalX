import {
  ActorRole,
  AgentResponse,
  AgentSloDTO,
  AlertDTO,
  ApprovalDTO,
  AuditChainVerificationDTO,
  AuditEventDTO,
  CostSummaryDTO,
  FetchRunsParams,
  LineageGraphDTO,
  PolicyCreateInput,
  PolicyDTO,
  PolicyUpdateInput,
  PricingVersionCreate,
  PricingVersionDTO,
  RunListItemResponse,
  RunSummaryDTO,
  SpanDTO,
  SystemConfigDTO,
  TeamDTO,
  UserSummaryDTO,
} from '@/types/telemetry';
import {
  type LoginResponse,
  getStoredToken,
  getStoredUser,
  setAuthSession,
} from '@/lib/auth';

export type ScenarioType =
  | 'normal'
  | 'hitl'
  | 'loop'
  | 'slow_loop'
  | 'cascade'
  | 'budget'
  | 'stall';

export interface SimulatorLaunchPayload {
  scenario: ScenarioType;
  team: string;
  live_llm: boolean;
}

export interface SimulatorLaunchResponse {
  run_id: string;
  scenario: ScenarioType;
  team: string;
  status: string;
}

export interface BootstrapAdminPayload {
  email: string;
  password: string;
  display_name: string;
}

export interface TeamCreatePayload {
  team_id: string;
  display_name: string;
  description?: string | null;
}

export interface UserCreatePayload {
  email: string;
  display_name: string;
  password: string;
  role: ActorRole;
  allowed_teams: string[];
}

export interface UserUpdatePayload {
  role?: ActorRole;
  allowed_teams?: string[];
  is_active?: boolean;
}

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

/**
 * Base fetch helper that automatically attaches Authorization: Bearer <token>
 * if a stored JWT session exists, or falls back to X-Actor-Id / X-Actor-Role headers.
 */
export async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit & { actorRole?: string; actorId?: string }
): Promise<T> {
  const url = endpoint.startsWith('http')
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const token = getStoredToken();
  const headers = new Headers(options?.headers || {});

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  } else if (options?.actorRole) {
    headers.set('X-Actor-Role', options.actorRole);
    headers.set('X-Actor-Id', options.actorId || 'lead-operator');
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorDetail = `${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

/**
 * Fetch all registered agents with dynamic health_status and active_runs_count.
 */
export async function fetchAgents(): Promise<AgentResponse[]> {
  const res = await fetch(`${API_BASE_URL}/api/agents`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch agents: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch per-agent Service Level Objective (SLO) metrics.
 */
export async function fetchAgentSlos(): Promise<AgentSloDTO[]> {
  const res = await fetch(`${API_BASE_URL}/api/agents/slos`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch agent SLOs: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch runs list with optional filters for status, team, and agent_id.
 */
export async function fetchRuns(
  params?: FetchRunsParams
): Promise<RunListItemResponse[]> {
  const url = new URL(`${API_BASE_URL}/api/runs`);
  if (params) {
    if (params.status) url.searchParams.set('status', params.status);
    if (params.team) url.searchParams.set('team', params.team);
    if (params.agent_id) url.searchParams.set('agent_id', params.agent_id);
    if (params.limit !== undefined) {
      url.searchParams.set('limit', String(params.limit));
    }
    if (params.offset !== undefined) {
      url.searchParams.set('offset', String(params.offset));
    }
  }

  const res = await fetch(url.toString(), {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch runs: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch detailed RunSummaryDTO by run ID.
 */
export async function fetchRunById(runId: string): Promise<RunSummaryDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}`,
    {
      cache: 'no-store',
    }
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch run ${runId}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch LineageGraphDTO for a given run ID.
 */
export async function fetchRunLineage(runId: string): Promise<LineageGraphDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/lineage`,
    {
      cache: 'no-store',
    }
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch lineage for run ${runId}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch chronological spans for audit replay timeline by run ID.
 */
export async function fetchRunEvents(runId: string): Promise<SpanDTO[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/events`,
    {
      cache: 'no-store',
    }
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch events for run ${runId}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch approval requests, optionally filtered by status ('PENDING', 'APPROVED', 'REJECTED').
 */
export async function fetchApprovals(status?: string): Promise<ApprovalDTO[]> {
  const url = new URL(`${API_BASE_URL}/api/approvals`);
  if (status) {
    url.searchParams.set('status', status);
  }
  const res = await fetch(url.toString(), {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch approvals: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Submit an approval decision (APPROVED or REJECTED) with RBAC actor role headers or JWT token.
 */
export async function submitApprovalDecision(
  approvalId: string,
  decision: 'APPROVED' | 'REJECTED',
  comment: string = '',
  actorRole: string = 'approver',
  actorId?: string,
): Promise<ApprovalDTO> {
  return apiFetch(
    `/api/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      actorRole,
      actorId,
      body: JSON.stringify({
        decision,
        comment: comment?.trim() || null,
      }),
    }
  );
}

/**
 * Fetch immutable governance audit log events (ordered descending, limit 100).
 */
export async function fetchAuditEvents(): Promise<AuditEventDTO[]> {
  return apiFetch('/api/audit-events', {
    cache: 'no-store',
  });
}

/**
 * Verify cryptographic SHA-256 hash-chain integrity of all recorded audit events.
 */
export async function verifyAuditChain(): Promise<AuditChainVerificationDTO> {
  return apiFetch('/api/audit-events/verify', {
    cache: 'no-store',
  });
}

/**
 * Fetch anomaly alerts, optionally filtered by run_id and acknowledgement status.
 */
export async function fetchAlerts(params?: {
  run_id?: string;
  acknowledged?: boolean;
  limit?: number;
}): Promise<AlertDTO[]> {
  const url = new URL(`${API_BASE_URL}/api/alerts`);
  if (params) {
    if (params.run_id) {
      url.searchParams.set('run_id', params.run_id);
    }
    if (params.acknowledged !== undefined) {
      url.searchParams.set('acknowledged', String(params.acknowledged));
    }
    if (params.limit !== undefined) {
      url.searchParams.set('limit', String(params.limit));
    }
  }
  const res = await fetch(url.toString(), {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch alerts: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Mark an anomaly alert as acknowledged.
 */
export async function acknowledgeAlert(alertId: string): Promise<AlertDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/alerts/${encodeURIComponent(alertId)}/ack`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );
  if (!res.ok) {
    let errorDetail = `${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

/**
 * Fetch fleet cost summary and slice breakdowns by agent, team, model, and run.
 */
export async function fetchCostSummary(): Promise<CostSummaryDTO> {
  const res = await fetch(`${API_BASE_URL}/api/costs/summary`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch cost summary: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch all pricing version rows ordered by effective_from descending.
 */
export async function fetchPricingVersions(): Promise<PricingVersionDTO[]> {
  const res = await fetch(`${API_BASE_URL}/api/costs/pricing`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch pricing versions: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Publish a new versioned pricing rate (requires approver/admin actor role).
 */
export async function createPricingVersion(
  payload: PricingVersionCreate,
  actorRole: string = 'approver'
): Promise<PricingVersionDTO> {
  return apiFetch('/api/costs/pricing', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    actorRole,
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch all governance policies ordered by enabled descending, updated_at descending.
 */
export async function fetchPolicies(): Promise<PolicyDTO[]> {
  return apiFetch('/api/policies', {
    cache: 'no-store',
  });
}

/**
 * Create a new governance policy (requires approver/admin role).
 */
export async function createPolicy(
  payload: PolicyCreateInput,
  actorRole: string = 'approver'
): Promise<PolicyDTO> {
  return apiFetch('/api/policies', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    actorRole,
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing governance policy (requires approver/admin role).
 */
export async function updatePolicy(
  policyId: string,
  payload: PolicyUpdateInput,
  actorRole: string = 'approver'
): Promise<PolicyDTO> {
  return apiFetch(`/api/policies/${encodeURIComponent(policyId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    actorRole,
    body: JSON.stringify(payload),
  });
}

/**
 * Immediately cancel a running or waiting run via operator kill-switch.
 */
export async function cancelRun(
  runId: string,
  actorRole: string = 'approver'
): Promise<RunSummaryDTO> {
  return apiFetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    actorRole,
  });
}

/**
 * Launch a simulated multi-agent chaos or demo scenario asynchronously.
 */
export async function launchSimulationScenario(
  payload: { scenario: ScenarioType; team: string; live_llm: boolean },
  actorRole?: string
): Promise<{ run_id: string; scenario: ScenarioType; team: string; status: string }> {
  const storedUser = getStoredUser();
  const effectiveRole = actorRole || storedUser?.role;
  return apiFetch('/api/simulator/run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    ...(effectiveRole ? { actorRole: effectiveRole } : {}),
    body: JSON.stringify(payload),
  });
}

async function parseErrorDetail(res: Response, fallbackPrefix: string): Promise<string> {
  let detail = `${fallbackPrefix} (${res.status} ${res.statusText})`;
  try {
    const errJson = (await res.json()) as { detail?: string };
    if (errJson && errJson.detail) {
      detail = errJson.detail;
    }
  } catch {
    // fallback
  }
  return detail;
}

/**
 * Fetch public system configuration (demo sandbox flag and first-admin bootstrap state).
 */
export async function fetchSystemConfig(): Promise<SystemConfigDTO> {
  const res = await fetch(`${API_BASE_URL}/api/system/config`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, 'Failed to fetch system config'));
  }
  return res.json();
}

/**
 * Initialize the first non-demo organization administrator and store the returned JWT.
 */
export async function bootstrapAdmin(
  payload: BootstrapAdminPayload
): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/bootstrap-admin`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: payload.email.trim().toLowerCase(),
      password: payload.password,
      display_name: payload.display_name.trim(),
    }),
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, 'Failed to initialize admin'));
  }
  const data = (await res.json()) as LoginResponse;
  setAuthSession(data.access_token, data.user);
  return data;
}

/**
 * Start a short-lived Demo Sandbox session using the demo approver account.
 */
export async function loginDemoSandbox(): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/demo-login`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(await parseErrorDetail(res, 'Failed to launch demo sandbox'));
  }
  const data = (await res.json()) as LoginResponse;
  setAuthSession(data.access_token, data.user);
  return data;
}

/**
 * Fetch all organizational teams ordered by display name.
 */
export async function fetchTeams(): Promise<TeamDTO[]> {
  return apiFetch('/api/teams', {
    cache: 'no-store',
  });
}

/**
 * Create a new organizational team (admin only).
 */
export async function createTeam(payload: TeamCreatePayload): Promise<TeamDTO> {
  return apiFetch('/api/teams', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch all non-demo organizational user accounts (admin only).
 */
export async function fetchUsers(): Promise<UserSummaryDTO[]> {
  return apiFetch('/api/users', {
    cache: 'no-store',
  });
}

/**
 * Provision a new organizational user account (admin only).
 */
export async function createUser(payload: UserCreatePayload): Promise<UserSummaryDTO> {
  return apiFetch('/api/users', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Update role, allowed_teams, or active status for an organizational user (admin only).
 */
export async function updateUser(
  userId: string,
  payload: UserUpdatePayload
): Promise<UserSummaryDTO> {
  return apiFetch(`/api/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}





