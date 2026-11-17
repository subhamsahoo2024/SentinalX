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
  run_id?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  span_type: SpanType;
  operation_name: string;
  status: SpanStatus;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  model?: ModelInfo | null;
  usage?: TokenUsage | null;
  cost?: CostInfo;
  error?: ErrorInfo | null;
  data?: Record<string, unknown>;
}

export interface LineageEdgeDTO {
  id: string;
  source: string;
  target: string;
  edge_type?: string | null;
  label?: string | null;
  data?: Record<string, unknown>;
}

export interface LineageGraphDTO {
  run_id: string;
  nodes: LineageNodeDTO[];
  edges: LineageEdgeDTO[];
  root_span_id?: string | null;
}

