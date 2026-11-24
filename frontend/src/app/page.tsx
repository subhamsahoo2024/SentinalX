'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import {
  Activity,
  AlertTriangle,
  Bot,
  Coins,
  Layers,
  PlayCircle,
  RefreshCw,
  Server,
  Zap,
  ArrowUpRight,
  Flame,
  CheckCircle2,
} from 'lucide-react';

import { fetchAgents, fetchAgentSlos, fetchAlerts, fetchRuns } from '@/lib/api';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import { cn } from '@/lib/cn';
import {
  AgentResponse,
  AgentSloDTO,
  AlertDTO,
  RunListItemResponse,
  SpanStatus,
  WebSocketMessage,
} from '@/types/telemetry';

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return dateStr;
  }
}

function formatDuration(
  startedAt?: string | null,
  endedAt?: string | null,
  status?: string
): string {
  if (!startedAt) return '—';
  const start = new Date(startedAt).getTime();
  if (isNaN(start)) return '—';

  if (endedAt) {
    const end = new Date(endedAt).getTime();
    if (isNaN(end)) return '—';
    const diffMs = Math.max(0, end - start);
    if (diffMs < 1000) return `${diffMs}ms`;
    if (diffMs < 60000) return `${(diffMs / 1000).toFixed(1)}s`;
    const mins = Math.floor(diffMs / 60000);
    const secs = Math.floor((diffMs % 60000) / 1000);
    return `${mins}m ${secs}s`;
  }

  if (status === 'RUNNING') {
    const now = Date.now();
    const diffMs = Math.max(0, now - start);
    if (diffMs < 60000) return `${Math.floor(diffMs / 1000)}s (live)`;
    return `${Math.floor(diffMs / 60000)}m (live)`;
  }

  return '—';
}

function StatusPill({ status }: { status: SpanStatus | string }) {
  const norm = (status || '').toUpperCase();

  switch (norm) {
    case 'RUNNING':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30 animate-pulse">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
          RUNNING
        </span>
      );
    case 'SUCCEEDED':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          SUCCEEDED
        </span>
      );
    case 'FAILED':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
          FAILED
        </span>
      );
    case 'STALLED':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-purple-500/10 text-purple-400 border border-purple-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
          STALLED
        </span>
      );
    case 'AWAITING_APPROVAL':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          APPROVAL REQ
        </span>
      );
    case 'TIMED_OUT':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-orange-500/10 text-orange-400 border border-orange-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-400" />
          TIMED OUT
        </span>
      );
    case 'CANCELLED':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
          CANCELLED
        </span>
      );
    case 'QUEUED':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800/80 text-slate-300 border border-slate-700">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
          QUEUED
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800/60 text-slate-400 border border-slate-700">
          {status}
        </span>
      );
  }
}

function formatSloLatency(p50: number | null, p95: number | null): string {
  if (p50 === null && p95 === null) return '—';
  const fmt = (ms: number | null) => {
    if (ms === null || isNaN(ms)) return '—';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };
  return `${fmt(p50)} / ${fmt(p95)}`;
}

export default function FleetOverviewPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [slos, setSlos] = useState<AgentSloDTO[]>([]);
  const [runs, setRuns] = useState<RunListItemResponse[]>([]);
  const [activeAlerts, setActiveAlerts] = useState<AlertDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshData = useCallback(async () => {
    setRefreshing(true);
    try {
      const [agentsData, runsData, alertsData, slosData] = await Promise.all([
        fetchAgents(),
        fetchRuns({ limit: 50 }),
        fetchAlerts({ acknowledged: false, limit: 10 }),
        fetchAgentSlos(),
      ]);
      setAgents(agentsData);
      setRuns(runsData);
      setActiveAlerts(alertsData);
      setSlos(slosData);
      setError(null);
    } catch (err: unknown) {
      console.warn('Failed to load fleet data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load telemetry data');
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Initial async load: runs in microtask, avoids synchronous setState in effect
  useEffect(() => {
    let isMounted = true;
    Promise.all([
      fetchAgents(),
      fetchRuns({ limit: 50 }),
      fetchAlerts({ acknowledged: false, limit: 10 }),
      fetchAgentSlos(),
    ])
      .then(([agentsData, runsData, alertsData, slosData]) => {
        if (isMounted) {
          setAgents(agentsData);
          setRuns(runsData);
          setActiveAlerts(alertsData);
          setSlos(slosData);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load telemetry data');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // WebSocket live updates on FLEET_UPDATED or ALERT_CREATED
  const handleWebSocketMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (
        msg &&
        (msg.type === 'FLEET_UPDATED' || msg.type === 'ALERT_CREATED')
      ) {
        refreshData();
      }
    },
    [refreshData]
  );

  useWebSocketStream<WebSocketMessage>('/ws/fleet', handleWebSocketMessage);

  // Map agents by agent_id for fast lookup
  const agentMap = useMemo(() => {
    const map = new Map<string, AgentResponse>();
    for (const a of agents) {
      map.set(a.agent_id, a);
    }
    return map;
  }, [agents]);

  // Map SLOs by agent_id for fast lookup
  const sloMap = useMemo(() => {
    const map = new Map<string, AgentSloDTO>();
    for (const s of slos) {
      map.set(s.agent_id, s);
    }
    return map;
  }, [slos]);

  // KPI calculations
  const activeAgentsCount = useMemo(() => {
    return agents.filter((a) => a.health_status === 'ACTIVE').length;
  }, [agents]);

  const runningTasksCount = useMemo(() => {
    return runs.filter(
      (r) => r.status === 'RUNNING' || r.status === 'QUEUED'
    ).length;
  }, [runs]);

  const failedOrStalledRunsCount = useMemo(() => {
    return runs.filter(
      (r) =>
        r.status === 'FAILED' ||
        r.status === 'STALLED' ||
        r.status === 'TIMED_OUT'
    ).length;
  }, [runs]);

  const spendInfo = useMemo(() => {
    let sum = 0;
    let hasKnown = false;
    for (const r of runs) {
      if (r.total_cost_usd !== null && r.total_cost_usd !== undefined) {
        sum += Number(r.total_cost_usd);
        hasKnown = true;
      }
    }

    if (!hasKnown) {
      return { formatted: 'Unknown', isUnknown: true };
    }

    const formatted =
      sum > 0 && sum < 0.01
        ? `$${sum.toFixed(4)}`
        : `$${sum.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;

    return { formatted, isUnknown: false };
  }, [runs]);

  const totalRecordedTokens = useMemo(() => {
    return runs.reduce((acc, r) => acc + (r.total_tokens || 0), 0);
  }, [runs]);

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-7xl mx-auto">
      {/* Overview Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-100">
            Fleet Control & Live Telemetry
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time status of connected AI agent workers, execution traces, and resource usage.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refreshData()}
            disabled={refreshing || loading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium text-slate-300 hover:text-slate-100 hover:bg-slate-800/80 transition-colors disabled:opacity-50"
            title="Refresh fleet data"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-cyan-400' : ''}`}
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/30 text-rose-300 text-sm flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => refreshData()}
            className="text-xs underline hover:text-rose-200"
          >
            Retry
          </button>
        </div>
      )}

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Active Agents */}
        <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-medium uppercase tracking-wider text-slate-400">
              Active Agents
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <Bot className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono tracking-tight text-slate-100">
              {loading ? '—' : activeAgentsCount}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              / {agents.length} total
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Heartbeats &lt; 60s</span>
          </div>
        </div>

        {/* Card 2: Running Tasks */}
        <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-medium uppercase tracking-wider text-slate-400">
              Running Tasks
            </span>
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <PlayCircle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono tracking-tight text-slate-100">
              {loading ? '—' : runningTasksCount}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              in-flight
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-blue-400" />
            <span>Active execution traces</span>
          </div>
        </div>

        {/* Card 3: Failed / Stalled Runs */}
        <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-medium uppercase tracking-wider text-slate-400">
              Failed / Stalled
            </span>
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                failedOrStalledRunsCount > 0
                  ? 'bg-rose-500/15 border border-rose-500/30 text-rose-400'
                  : 'bg-slate-800 border border-slate-700 text-slate-400'
              }`}
            >
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span
              className={`text-3xl font-bold font-mono tracking-tight ${
                failedOrStalledRunsCount > 0 ? 'text-rose-400' : 'text-slate-100'
              }`}
            >
              {loading ? '—' : failedOrStalledRunsCount}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              traces
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {failedOrStalledRunsCount > 0 ? (
              <span className="text-rose-400 font-medium">Attention required</span>
            ) : (
              <span>Zero errors detected</span>
            )}
          </div>
        </div>

        {/* Card 4: Total Recorded Spend */}
        <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-medium uppercase tracking-wider text-slate-400">
              Total Spend
            </span>
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <Coins className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span
              className={`text-3xl font-bold font-mono tracking-tight ${
                spendInfo.isUnknown ? 'text-slate-400 text-2xl' : 'text-slate-100'
              }`}
            >
              {loading ? '—' : spendInfo.formatted}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-400 font-mono">
            {loading ? '—' : `${totalRecordedTokens.toLocaleString()} tokens`}
          </div>
        </div>
      </div>

      {/* Active Anomaly Alerts */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Flame className="w-4 h-4 text-rose-400" />
            <h3 className="text-lg font-semibold text-slate-100 tracking-tight">
              Active Anomaly Alerts
            </h3>
            {activeAlerts.length > 0 ? (
              <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">
                {activeAlerts.length} unresolved
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-slate-400 border border-slate-700">
                0
              </span>
            )}
          </div>
        </div>

        {loading ? (
          <div className="h-20 rounded-xl bg-slate-900/30 border border-slate-800/80 animate-pulse" />
        ) : activeAlerts.length === 0 ? (
          <div className="p-4 rounded-xl bg-slate-900/30 border border-slate-800/80 flex items-center gap-3 text-slate-400 text-xs font-mono">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              All agent execution policies within normal operating thresholds. Zero active tool loops, budget overruns, or cascading failures detected.
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {activeAlerts.map((alert) => {
              const isCrit = alert.severity === 'CRITICAL';
              const isHigh = alert.severity === 'HIGH';
              const isMed = alert.severity === 'MEDIUM';

              const badgeStyle = isCrit
                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                : isHigh
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                : isMed
                ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40'
                : 'bg-sky-500/20 text-sky-300 border-sky-500/40';

              const cardBorder = isCrit
                ? 'border-rose-500/30 hover:border-rose-500/50'
                : isHigh
                ? 'border-amber-500/30 hover:border-amber-500/50'
                : 'border-slate-800 hover:border-slate-700';

              return (
                <div
                  key={alert.alert_id}
                  className={cn(
                    'p-4 rounded-xl bg-slate-900/60 border backdrop-blur-sm transition-all flex flex-col justify-between gap-3 shadow-sm',
                    cardBorder
                  )}
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border',
                            badgeStyle
                          )}
                        >
                          {alert.severity}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                          {alert.rule_id}
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-slate-400">
                        {formatRelativeTime(alert.created_at)}
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-slate-100 line-clamp-2">
                      {alert.title}
                    </h4>

                    {/* Evidence summary */}
                    {alert.evidence && Object.keys(alert.evidence).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {Object.entries(alert.evidence).map(([k, v]) => (
                          <span
                            key={k}
                            className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/80 text-slate-300 border border-slate-700/60 max-w-full truncate"
                          >
                            <span className="text-slate-400">{k}:</span>{' '}
                            {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Footer link to run */}
                  <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-xs font-mono">
                    <Link
                      href={`/runs/${encodeURIComponent(alert.run_id)}`}
                      className="inline-flex items-center gap-1 font-semibold text-cyan-400 hover:text-cyan-300 transition-colors group"
                    >
                      <span className="truncate max-w-[150px]">Run: {alert.run_id}</span>
                      <ArrowUpRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                    </Link>

                    {alert.impacted_span_ids && alert.impacted_span_ids.length > 0 && (
                      <span className="text-[11px] text-rose-400/90 font-medium">
                        {alert.impacted_span_ids.length} span{alert.impacted_span_ids.length > 1 ? 's' : ''} impacted
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Registered Agents Grid */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Server className="w-4 h-4 text-cyan-400" />
            <h3 className="text-lg font-semibold text-slate-100 tracking-tight">
              Registered Agents
            </h3>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-slate-300 border border-slate-700">
              {agents.length}
            </span>
          </div>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-44 rounded-xl bg-slate-900/30 border border-slate-800/80 animate-pulse"
              />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <div className="p-8 rounded-xl bg-slate-900/30 border border-slate-800 text-center space-y-2">
            <Bot className="w-8 h-8 text-slate-400 mx-auto" />
            <div className="text-sm font-medium text-slate-300">
              No agents registered yet
            </div>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Initialize the Sentinel SDK or post telemetry events to register agents with the Control Tower.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {agents.map((agent) => {
              const isHealthy = agent.health_status === 'ACTIVE';
              const isIdle = agent.health_status === 'IDLE';
              const slo = sloMap.get(agent.agent_id);
              const successRate = slo ? slo.success_rate_pct : 100.0;
              const successRateClass =
                successRate >= 95
                  ? 'text-emerald-400'
                  : successRate >= 80
                  ? 'text-amber-400'
                  : 'text-rose-400';
              const totalInvocations = slo ? slo.total_invocations : 0;
              const anomalyCount = slo ? slo.anomaly_count : 0;

              return (
                <div
                  key={agent.agent_id}
                  className="p-5 rounded-xl bg-slate-900/50 border border-slate-800 hover:border-slate-700/80 transition-all flex flex-col justify-between space-y-4"
                >
                  <div className="space-y-3">
                    {/* Header: Name and Health Dot */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h4
                          className="font-semibold text-slate-100 text-sm truncate"
                          title={agent.display_name}
                        >
                          {agent.display_name}
                        </h4>
                        <div
                          className="text-xs font-mono text-slate-400 truncate mt-0.5"
                          title={agent.agent_id}
                        >
                          {agent.agent_id}
                        </div>
                      </div>

                      {/* Health Status Indicator */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {isHealthy ? (
                          <>
                            <span className="relative flex h-2 w-2">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                            </span>
                            <span className="text-[11px] font-mono text-emerald-400 uppercase">
                              Active
                            </span>
                          </>
                        ) : isIdle ? (
                          <>
                            <span className="w-2 h-2 rounded-full bg-amber-400" />
                            <span className="text-[11px] font-mono text-amber-400 uppercase">
                              Idle
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="w-2 h-2 rounded-full bg-slate-500" />
                            <span className="text-[11px] font-mono text-slate-400 uppercase">
                              Offline
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Metadata Pills */}
                    <div className="flex flex-wrap gap-1.5">
                      <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                        {agent.framework || 'custom'}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/80 text-slate-300 border border-slate-700/60">
                        team: {agent.team || 'default'}
                      </span>
                      {agent.environment && (
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/50 text-slate-400 border border-slate-700/40">
                          {agent.environment}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Compact 3-Column SLO Strip */}
                  <div className="pt-3 border-t border-slate-800/60 grid grid-cols-3 gap-2 text-center text-xs font-mono">
                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">
                        Success
                      </span>
                      <span className={cn('font-bold', successRateClass)}>
                        {slo ? `${slo.success_rate_pct.toFixed(1)}%` : '100.0%'}
                      </span>
                    </div>

                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">
                        p50 / p95
                      </span>
                      <span className="font-semibold text-slate-200 truncate max-w-full">
                        {formatSloLatency(
                          slo?.p50_duration_ms ?? null,
                          slo?.p95_duration_ms ?? null
                        )}
                      </span>
                    </div>

                    <div className="flex flex-col items-center">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">
                        Invocations
                      </span>
                      <div className="flex items-center gap-1">
                        <span className="font-semibold text-slate-200">
                          {totalInvocations}
                        </span>
                        {anomalyCount > 0 && (
                          <span
                            className={cn(
                              'px-1.5 py-0.2 rounded text-[9px] font-bold border',
                              anomalyCount >= 5
                                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                                : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                            )}
                            title={`${anomalyCount} anomalies recorded`}
                          >
                            {anomalyCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Card Footer: Active Runs & Last Seen */}
                  <div className="pt-2 border-t border-slate-800/40 flex items-center justify-between text-xs text-slate-400 font-mono">
                    <div className="flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5 text-cyan-400" />
                      <span>{agent.active_runs_count} active</span>
                    </div>
                    <span title={agent.last_seen_at}>
                      {formatRelativeTime(agent.last_seen_at)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Recent Runs Table */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h3 className="text-lg font-semibold text-slate-100 tracking-tight">
              Recent Runs
            </h3>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-slate-300 border border-slate-700">
              {runs.length}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/80 text-xs font-mono uppercase text-slate-400 tracking-wider">
                  <th className="py-3 px-4">Run ID</th>
                  <th className="py-3 px-4">Root Agent</th>
                  <th className="py-3 px-4">Team</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">Tokens</th>
                  <th className="py-3 px-4">Cost</th>
                  <th className="py-3 px-4">Started</th>
                  <th className="py-3 px-2 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-slate-400">
                      <div className="flex items-center justify-center gap-2">
                        <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
                        <span>Loading execution runs...</span>
                      </div>
                    </td>
                  </tr>
                ) : runs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-slate-400">
                      No execution runs recorded yet.
                    </td>
                  </tr>
                ) : (
                  runs.map((run) => {
                    const agentName =
                      run.root_agent_id && agentMap.has(run.root_agent_id)
                        ? agentMap.get(run.root_agent_id)!.display_name
                        : run.root_agent_id || '—';

                    return (
                      <tr
                        key={run.run_id}
                        onClick={() => router.push(`/runs/${encodeURIComponent(run.run_id)}`)}
                        className="hover:bg-slate-800/40 cursor-pointer transition-colors group"
                      >
                        {/* Run ID */}
                        <td className="py-3 px-4 font-mono text-xs text-cyan-400 group-hover:text-cyan-300 font-medium">
                          {run.run_id}
                        </td>

                        {/* Root Agent */}
                        <td className="py-3 px-4 text-xs font-medium text-slate-200">
                          <div className="flex items-center gap-1.5">
                            <Bot className="w-3.5 h-3.5 text-slate-400 group-hover:text-cyan-400 transition-colors" />
                            <span className="truncate max-w-[160px]" title={agentName}>
                              {agentName}
                            </span>
                          </div>
                        </td>

                        {/* Team */}
                        <td className="py-3 px-4 text-xs font-mono text-slate-400">
                          {run.team || 'default'}
                        </td>

                        {/* Status */}
                        <td className="py-3 px-4">
                          <StatusPill status={run.status} />
                        </td>

                        {/* Duration */}
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">
                          {formatDuration(run.started_at, run.ended_at, run.status)}
                        </td>

                        {/* Tokens */}
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">
                          {run.total_tokens ? run.total_tokens.toLocaleString() : '0'}
                        </td>

                        {/* Cost */}
                        <td className="py-3 px-4 font-mono text-xs text-slate-300">
                          {run.total_cost_usd !== null && run.total_cost_usd !== undefined ? (
                            `$${Number(run.total_cost_usd).toFixed(4)}`
                          ) : (
                            <span className="text-slate-400 italic">Unknown</span>
                          )}
                        </td>

                        {/* Started */}
                        <td
                          className="py-3 px-4 text-xs text-slate-400"
                          title={run.started_at}
                        >
                          {formatRelativeTime(run.started_at)}
                        </td>

                        {/* Arrow link */}
                        <td className="py-3 px-2 text-right text-slate-400 group-hover:text-cyan-400 transition-colors">
                          <ArrowUpRight className="w-4 h-4 ml-auto" />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
