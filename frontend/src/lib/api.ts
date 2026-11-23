import {
  AgentResponse,
  AlertDTO,
  ApprovalDTO,
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
} from '@/types/telemetry';

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

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
 * Submit an approval decision (APPROVED or REJECTED) with RBAC actor role headers.
 */
export async function submitApprovalDecision(
  approvalId: string,
  decision: 'APPROVED' | 'REJECTED',
  comment: string,
  actorRole: string
): Promise<ApprovalDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'lead-operator',
        'X-Actor-Role': actorRole,
      },
      body: JSON.stringify({
        decision,
        comment: comment.trim() || null,
      }),
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
 * Fetch immutable governance audit log events (ordered descending, limit 100).
 */
export async function fetchAuditEvents(): Promise<AuditEventDTO[]> {
  const res = await fetch(`${API_BASE_URL}/api/audit-events`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch audit events: ${res.status} ${res.statusText}`);
  }
  return res.json();
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
  const res = await fetch(`${API_BASE_URL}/api/costs/pricing`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Actor-Id': 'lead-operator',
      'X-Actor-Role': actorRole,
    },
    body: JSON.stringify(payload),
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
 * Fetch all governance policies ordered by enabled descending, updated_at descending.
 */
export async function fetchPolicies(): Promise<PolicyDTO[]> {
  const res = await fetch(`${API_BASE_URL}/api/policies`, {
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch policies: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/**
 * Create a new governance policy (requires approver/admin role).
 */
export async function createPolicy(
  payload: PolicyCreateInput,
  actorRole: string = 'approver'
): Promise<PolicyDTO> {
  const res = await fetch(`${API_BASE_URL}/api/policies`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Actor-Id': 'lead-operator',
      'X-Actor-Role': actorRole,
    },
    body: JSON.stringify(payload),
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
 * Update an existing governance policy (requires approver/admin role).
 */
export async function updatePolicy(
  policyId: string,
  payload: PolicyUpdateInput,
  actorRole: string = 'approver'
): Promise<PolicyDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/policies/${encodeURIComponent(policyId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'lead-operator',
        'X-Actor-Role': actorRole,
      },
      body: JSON.stringify(payload),
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
 * Immediately cancel a running or waiting run via operator kill-switch.
 */
export async function cancelRun(
  runId: string,
  actorRole: string = 'approver'
): Promise<RunSummaryDTO> {
  const res = await fetch(
    `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Actor-Id': 'lead-operator',
        'X-Actor-Role': actorRole,
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




