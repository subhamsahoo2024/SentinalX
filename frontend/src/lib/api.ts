import {
  AgentResponse,
  FetchRunsParams,
  RunListItemResponse,
  RunSummaryDTO,
} from '@/types/telemetry';

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
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

