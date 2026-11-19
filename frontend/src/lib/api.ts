import {
  AgentResponse,
  AlertDTO,
  ApprovalDTO,
  AuditEventDTO,
  FetchRunsParams,
  LineageGraphDTO,
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


