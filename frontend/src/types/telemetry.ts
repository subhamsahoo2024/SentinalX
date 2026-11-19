/**
 * Canonical Event v1.0 schema and telemetry types for SentinelX.
 * Mirrors Python schemas in sentinel_sdk.schema and sentinel_backend.schemas.telemetry.
 */

export type SpanType = 'AGENT' | 'LLM' | 'TOOL' | 'APPROVAL';

export type SpanStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'AWAITING_APPROVAL'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'TIMED_OUT'
  | 'CANCELLED'
  | 'STALLED';

export type CostBasis = 'EXACT' | 'ESTIMATED' | 'UNKNOWN';

export interface ModelInfo {
  provider?: string | null;
  name?: string | null;
}

export interface TokenUsage {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_tokens?: number | null;
}

export interface CostInfo {
  amount_usd?: number | null;
  currency?: string;
  basis?: CostBasis;
  pricing_version?: string | null;
}

export interface ErrorInfo {
  error_class: string;
  message: string;
  stack_summary?: string | null;
}

export interface CanonicalEventV1 {
  schema_version?: '1.0';
  event_id: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  run_id: string;
  agent_id: string;
  agent_name?: string | null;
  team?: string;
  framework?: string;
  attempt_number?: number;
  span_type: SpanType;
  operation_name: string;
  status: SpanStatus;
  started_at: string;
  ended_at?: string | null;
  model?: ModelInfo | null;
  usage?: TokenUsage | null;
  cost?: CostInfo;
  error?: ErrorInfo | null;
  attributes?: Record<string, unknown>;
}

export interface TelemetryBatchRequest {
  events: CanonicalEventV1[];
}

export interface RunSummaryDTO {
  run_id: string;
  trace_id?: string | null;
  agent_id: string;
  agent_name?: string | null;
  team?: string;
  framework?: string;
  status: SpanStatus;
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  total_spans?: number;
  total_tokens?: number;
  total_cost_usd?: number;
  error_count?: number;
}

export interface LineageNodeDTO {
  id: string;
  span_id: string;
  parent_span_id?: string | null;
  agent_id: string;
  attempt_number?: number;
  span_type: SpanType | string;
  operation_name: string;
  status: SpanStatus | string;
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  model_provider?: string | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  direct_cost_usd?: number | null;
  cost_basis?: CostBasis | string;
  is_root_cause?: boolean;
  error_class?: string | null;
  error_message?: string | null;
  attributes?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LineageEdgeDTO {
  id: string;
  source: string;
  target: string;
  is_failed_path: boolean;
}

export interface LineageGraphDTO {
  run_id: string;
  trace_id: string;
  status: SpanStatus | string;
  nodes: LineageNodeDTO[];
  edges: LineageEdgeDTO[];
  orphan_span_ids: string[];
}

export interface SpanDTO {
  span_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  run_id: string;
  agent_id: string;
  attempt_number: number;
  span_type: SpanType | string;
  operation_name: string;
  status: SpanStatus | string;
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  model_provider?: string | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_tokens?: number | null;
  direct_cost_usd?: number | null;
  cost_basis?: CostBasis | string;
  is_root_cause?: boolean;
  error_class?: string | null;
  error_message?: string | null;
  attributes?: Record<string, unknown>;
}

export type HealthStatus = 'ACTIVE' | 'IDLE' | 'OFFLINE';

export interface AgentResponse {
  agent_id: string;
  display_name: string;
  framework: string;
  team: string;
  environment: string;
  declared_tools: unknown[];
  status: string;
  last_seen_at: string;
  health_status: HealthStatus;
  active_runs_count: number;
}

export interface RunListItemResponse {
  run_id: string;
  trace_id: string;
  root_agent_id: string | null;
  team: string;
  status: SpanStatus | string;
  started_at: string;
  ended_at: string | null;
  last_event_at: string;
  total_tokens: number;
  total_cost_usd: number | null;
  cost_status: CostBasis | string;
  span_count: number;
  alert_count: number;
}

export interface FetchRunsParams {
  status?: string;
  team?: string;
  agent_id?: string;
  limit?: number;
  offset?: number;
}

export interface FleetUpdatedPayload {
  affected_run_ids?: string[];
  affected_agent_ids?: string[];
  event_count?: number;
}

export interface WebSocketMessage<T = unknown> {
  type: string;
  timestamp: string;
  data: T;
}
