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
  rolled_up_cost_usd?: number | null;
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

export type ActorRole = 'viewer' | 'operator' | 'approver' | 'admin';

export interface ApprovalDTO {
  approval_id: string;
  run_id: string;
  span_id: string;
  agent_id: string;
  tool_name: string;
  sanitized_args: Record<string, unknown>;
  risk_level: string;
  policy_reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | string;
  decided_by?: string | null;
  decided_at?: string | null;
  comment?: string | null;
  created_at: string;
}

export interface AlertDTO {
  alert_id: string;
  run_id: string;
  origin_span_id?: string | null;
  rule_id: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  title: string;
  evidence: Record<string, unknown>;
  impacted_span_ids: string[];
  acknowledged: boolean;
  created_at: string;
}

export interface AuditEventDTO {
  audit_id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  prev_hash?: string;
  entry_hash?: string;
  created_at: string;
}

export interface AuditChainVerificationDTO {
  valid: boolean;
  total_events: number;
  latest_hash: string | null;
  broken_at_audit_id: string | null;
}

export interface SentinelUser {
  user_id: string;
  email: string;
  display_name: string;
  role: ActorRole | string;
  allowed_teams: string[];
  is_demo: boolean;
}

export interface SystemConfigDTO {
  demo_sandbox_enabled: boolean;
  needs_bootstrap: boolean;
}

export interface TeamDTO {
  team_id: string;
  display_name: string;
  description?: string | null;
  created_at: string;
}

export interface UserSummaryDTO {
  user_id: string;
  email: string;
  display_name: string;
  role: ActorRole | string;
  allowed_teams: string[];
  is_active: boolean;
  created_at: string;
}

export interface ApiKeyDTO {
  key_id: string;
  name: string;
  team: string;
  key_prefix: string;
  created_by: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyCreatedDTO extends ApiKeyDTO {
  raw_key: string;
}

export type ScenarioType =
  | 'normal'
  | 'hitl'
  | 'loop'
  | 'slow_loop'
  | 'cascade'
  | 'budget'
  | 'stall';

export interface LaunchScenarioPayload {
  scenario: ScenarioType;
  team?: string;
  live_llm?: boolean;
}

export interface LaunchScenarioResponse {
  run_id: string;
  trace_id?: string;
  scenario: ScenarioType;
  team?: string;
  status: string;
  message?: string;
}

export interface PricingVersionCreate {
  provider: string;
  model_name: string;
  version_tag: string;
  input_rate_per_1m: number;
  output_rate_per_1m: number;
}

export interface PricingVersionDTO {
  id: number;
  provider: string;
  model_name: string;
  version_tag: string;
  input_rate_per_1m: number;
  output_rate_per_1m: number;
  effective_from: string;
}

export interface CostBreakdownItemDTO {
  key: string;
  label: string;
  run_count: number;
  span_count: number;
  input_tokens: number;
  output_tokens: number;
  total_cost_usd: number | null;
  unknown_spans_count: number;
}

export interface CostSummaryDTO {
  total_known_cost_usd: number;
  total_tokens: number;
  unknown_usage_spans_count: number;
  by_agent: CostBreakdownItemDTO[];
  by_team: CostBreakdownItemDTO[];
  by_model: CostBreakdownItemDTO[];
  by_run: CostBreakdownItemDTO[];
}

export interface PolicyDTO {
  policy_id: string;
  name: string;
  team?: string | null;
  agent_id?: string | null;
  max_tokens: number;
  max_cost_usd: number;
  loop_threshold: number;
  loop_window_sec: number;
  auto_block_on_budget: boolean;
  protected_tools: string[];
  enabled: boolean;
  updated_at: string;
}

export interface PolicyCreateInput {
  name: string;
  team?: string | null;
  agent_id?: string | null;
  max_tokens?: number;
  max_cost_usd?: number;
  loop_threshold?: number;
  loop_window_sec?: number;
  auto_block_on_budget?: boolean;
  protected_tools?: string[];
  enabled?: boolean;
}

export interface PolicyUpdateInput {
  name?: string;
  team?: string | null;
  agent_id?: string | null;
  max_tokens?: number;
  max_cost_usd?: number;
  loop_threshold?: number;
  loop_window_sec?: number;
  auto_block_on_budget?: boolean;
  protected_tools?: string[];
  enabled?: boolean;
}

export interface AgentSloDTO {
  agent_id: string;
  display_name: string;
  framework: string;
  team: string;
  total_invocations: number;
  succeeded_count: number;
  failed_count: number;
  success_rate_pct: number;
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  avg_tokens_per_call: number;
  anomaly_count: number;
}


