import {
  ActorRole,
  AgentResponse,
  AgentSloDTO,
  AlertDTO,
  ApiKeyCreatedDTO,
  ApiKeyDTO,
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
  WebhookCreateInput,
  WebhookEndpointDTO,
  WebhookTestResultDTO,
  WebhookUpdateInput,
} from '@/types/telemetry';
import {
  type LoginResponse,
  TOKEN_KEY,
  clearAuthSession,
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
    if (res.status === 401 && typeof window !== 'undefined') {
      const hasRawToken = Boolean(window.localStorage.getItem(TOKEN_KEY));
      if (token || hasRawToken) {
        clearAuthSession();
      }
    }
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
 * Verify the stored JWT session against GET /api/auth/me and clear it on 401/403.
 */
export async function verifyCurrentSession(): Promise<boolean> {
  const token = getStoredToken();
  if (!token) {
    return false;
  }
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      cache: 'no-store',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (res.status === 401 || res.status === 403) {
      clearAuthSession();
      return false;
    }
    return res.ok;
  } catch {
    return true;
  }
}

/**
 * Fetch all registered agents with dynamic health_status and active_runs_count.
 */
export async function fetchAgents(): Promise<AgentResponse[]> {
  return apiFetch('/api/agents', {
    cache: 'no-store',
  });
}

/**
 * Fetch per-agent Service Level Objective (SLO) metrics.
 */
export async function fetchAgentSlos(): Promise<AgentSloDTO[]> {
  return apiFetch('/api/agents/slos', {
    cache: 'no-store',
  });
}

/**
 * Fetch runs list with optional filters for status, team, and agent_id.
 */
export async function fetchRuns(
  params?: FetchRunsParams
): Promise<RunListItemResponse[]> {
  const search = new URLSearchParams();
  if (params) {
    if (params.status) search.set('status', params.status);
    if (params.team) search.set('team', params.team);
    if (params.agent_id) search.set('agent_id', params.agent_id);
    if (params.limit !== undefined) {
      search.set('limit', String(params.limit));
    }
    if (params.offset !== undefined) {
      search.set('offset', String(params.offset));
    }
  }
  const qs = search.toString();
  return apiFetch(`/api/runs${qs ? `?${qs}` : ''}`, {
    cache: 'no-store',
  });
}

/**
 * Fetch detailed RunSummaryDTO by run ID.
 */
export async function fetchRunById(runId: string): Promise<RunSummaryDTO> {
  return apiFetch(`/api/runs/${encodeURIComponent(runId)}`, {
    cache: 'no-store',
  });
}

/**
 * Fetch LineageGraphDTO for a given run ID.
 */
export async function fetchRunLineage(runId: string): Promise<LineageGraphDTO> {
  return apiFetch(`/api/runs/${encodeURIComponent(runId)}/lineage`, {
    cache: 'no-store',
  });
}

/**
 * Fetch chronological spans for audit replay timeline by run ID.
 */
export async function fetchRunEvents(runId: string): Promise<SpanDTO[]> {
  return apiFetch(`/api/runs/${encodeURIComponent(runId)}/events`, {
    cache: 'no-store',
  });
}

/**
 * Fetch approval requests, optionally filtered by status ('PENDING', 'APPROVED', 'REJECTED').
 */
export async function fetchApprovals(status?: string): Promise<ApprovalDTO[]> {
  const search = new URLSearchParams();
  if (status) {
    search.set('status', status);
  }
  const qs = search.toString();
  return apiFetch(`/api/approvals${qs ? `?${qs}` : ''}`, {
    cache: 'no-store',
  });
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
  const search = new URLSearchParams();
  if (params) {
    if (params.run_id) {
      search.set('run_id', params.run_id);
    }
    if (params.acknowledged !== undefined) {
      search.set('acknowledged', String(params.acknowledged));
    }
    if (params.limit !== undefined) {
      search.set('limit', String(params.limit));
    }
  }
  const qs = search.toString();
  return apiFetch(`/api/alerts${qs ? `?${qs}` : ''}`, {
    cache: 'no-store',
  });
}

/**
 * Mark an anomaly alert as acknowledged.
 */
export async function acknowledgeAlert(alertId: string): Promise<AlertDTO> {
  return apiFetch(`/api/alerts/${encodeURIComponent(alertId)}/ack`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Fetch fleet cost summary and slice breakdowns by agent, team, model, and run.
 */
export async function fetchCostSummary(): Promise<CostSummaryDTO> {
  return apiFetch('/api/costs/summary', {
    cache: 'no-store',
  });
}

/**
 * Fetch all pricing version rows ordered by effective_from descending.
 */
export async function fetchPricingVersions(): Promise<PricingVersionDTO[]> {
  return apiFetch('/api/costs/pricing', {
    cache: 'no-store',
  });
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

/**
 * List all minted team-bound ingestion API keys (non-demo admin only).
 */
export async function fetchApiKeys(): Promise<ApiKeyDTO[]> {
  return apiFetch('/api/api-keys', {
    cache: 'no-store',
  });
}

/**
 * Mint a new team-bound ingestion API key and return the one-time raw secret.
 */
export async function createApiKey(payload: {
  name: string;
  team: string;
}): Promise<ApiKeyCreatedDTO> {
  return apiFetch('/api/api-keys', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Soft-revoke an active team-bound API key (non-demo admin only).
 */
export async function revokeApiKey(
  keyId: string
): Promise<{ status: string; key_id: string }> {
  return apiFetch(`/api/api-keys/${encodeURIComponent(keyId)}`, {
    method: 'DELETE',
  });
}

/**
 * List all configured outbound webhook endpoints (non-demo admin only).
 */
export async function fetchWebhooks(): Promise<WebhookEndpointDTO[]> {
  return apiFetch('/api/webhooks', {
    cache: 'no-store',
  });
}

/**
 * Create a new outbound incident webhook endpoint (non-demo admin only).
 */
export async function createWebhook(
  payload: WebhookCreateInput
): Promise<WebhookEndpointDTO> {
  return apiFetch('/api/webhooks', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Update an outbound webhook endpoint configuration or enabled state.
 */
export async function updateWebhook(
  webhookId: string,
  payload: WebhookUpdateInput
): Promise<WebhookEndpointDTO> {
  return apiFetch(`/api/webhooks/${encodeURIComponent(webhookId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Delete an outbound webhook endpoint permanently.
 */
export async function deleteWebhook(
  webhookId: string
): Promise<{ status: string; webhook_id: string }> {
  return apiFetch(`/api/webhooks/${encodeURIComponent(webhookId)}`, {
    method: 'DELETE',
  });
}

/**
 * Trigger an immediate TEST_PING delivery to verify webhook connectivity.
 */
export async function testWebhook(
  webhookId: string
): Promise<WebhookTestResultDTO> {
  return apiFetch(`/api/webhooks/${encodeURIComponent(webhookId)}/test`, {
    method: 'POST',
  });
}





