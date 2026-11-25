'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import { AgentProfileModal } from '@/components/AgentProfileModal';
import { StatusBadge } from '@/components/StatusBadge';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import {
  acknowledgeAlert,
  fetchAgentSlos,
  fetchAgents,
  fetchAlerts,
  fetchRuns,
} from '@/lib/api';
import {
  computeRunDurationMs,
  formatDurationMs,
  formatRelativeTime,
  formatTokens,
  formatUsd,
} from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  AgentResponse,
  AgentSloDTO,
  AlertDTO,
  RunListItemResponse,
  WebSocketMessage,
} from '@/types/telemetry';

export default function FleetOverviewPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [slos, setSlos] = useState<AgentSloDTO[]>([]);
  const [runs, setRuns] = useState<RunListItemResponse[]>([]);
  const [alerts, setAlerts] = useState<AlertDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<AgentResponse | null>(null);

  const loadFleetData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [agentData, sloData, runData, alertData] = await Promise.all([
        fetchAgents(),
        fetchAgentSlos(),
        fetchRuns({ limit: 50 }),
        fetchAlerts({ acknowledged: false, limit: 10 }),
      ]);
      setAgents(agentData);
      setSlos(sloData);
      setRuns(runData);
      setAlerts(alertData);
      setError(null);
    } catch (err: unknown) {
      console.warn('Failed to load fleet data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load telemetry data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadFleetData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadFleetData]);

  const handleWsMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (msg.type === 'FLEET_UPDATED' || msg.type === 'ALERT_CREATED') {
        void loadFleetData();
      }
    },
    [loadFleetData],
  );

  useWebSocketStream<WebSocketMessage>('/ws/fleet', handleWsMessage);

  const sloByAgent = useMemo(() => {
    const map = new Map<string, AgentSloDTO>();
    for (const s of slos) map.set(s.agent_id, s);
    return map;
  }, [slos]);

  const agentNameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of agents) map.set(a.agent_id, a.display_name);
    return map;
  }, [agents]);

  const kpis = useMemo(() => {
    const activeAgents = agents.filter((a) => a.health_status === 'ACTIVE').length;
    const runningTasks = runs.filter(
      (r) => r.status === 'RUNNING' || r.status === 'QUEUED',
    ).length;
    const failedOrStalled = runs.filter(
      (r) =>
        r.status === 'FAILED' || r.status === 'STALLED' || r.status === 'TIMED_OUT',
    ).length;
    const totalSpend = runs.reduce((acc, r) => acc + (r.total_cost_usd ?? 0), 0);
    const totalTokens = runs.reduce((acc, r) => acc + (r.total_tokens ?? 0), 0);
    return {
      activeAgents,
      totalAgents: agents.length,
      runningTasks,
      failedOrStalled,
      totalSpend,
      totalTokens,
    };
  }, [agents, runs]);

  const handleAcknowledge = async (alertId: string) => {
    try {
      await acknowledgeAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
    } catch (err: unknown) {
      console.warn('Failed to acknowledge alert:', err);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Agent Fleet & Execution Traces
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Real-time worker health, SLO latency telemetry, anomaly alerts, and lineage runs.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadFleetData(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] px-4 py-2 text-xs font-medium text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247] disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')}
            aria-hidden="true"
          />
          <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/40 px-4 py-3 flex items-center justify-between gap-3 text-xs text-red-700 dark:text-red-300">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => void loadFleetData(true)}
            className="font-medium underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      <section
        aria-label="Fleet Summary Metrics"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Agents</p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-[#041533] dark:text-slate-100">
            {loading ? '—' : kpis.activeAgents}{' '}
            <span className="text-sm font-normal text-slate-400 dark:text-slate-500">
              / {kpis.totalAgents}
            </span>
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Running Tasks</p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-[#0257D5] dark:text-[#00C2FF]">
            {loading ? '—' : kpis.runningTasks}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Failed / Stalled Traces
          </p>
          <p
            className={cn(
              'mt-2 text-2xl font-semibold font-mono tabular-nums',
              kpis.failedOrStalled > 0
                ? 'text-red-700 dark:text-red-400'
                : 'text-slate-900 dark:text-slate-100',
            )}
          >
            {loading ? '—' : kpis.failedOrStalled}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Total Trace Spend
          </p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-slate-900 dark:text-slate-100">
            {loading ? '—' : formatUsd(kpis.totalSpend)}
          </p>
          <p className="mt-1 text-xs font-mono tabular-nums text-slate-500 dark:text-slate-400">
            {loading ? '—' : `${formatTokens(kpis.totalTokens)} tokens`}
          </p>
        </div>
      </section>

      {alerts.length > 0 && (
        <section aria-label="Active Anomaly Alerts" className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" aria-hidden="true" />
              <span>Active Anomaly Alerts ({alerts.length})</span>
            </h3>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className="rounded-lg border border-red-200 dark:border-red-800/80 bg-white dark:bg-[#07152E] px-4 py-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3"
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <StatusBadge status={alert.severity} compact />
                    <span className="font-mono text-xs font-semibold text-red-800 dark:text-red-300">
                      {alert.rule_id}
                    </span>
                    <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {alert.title}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {formatRelativeTime(alert.created_at)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
                    {Object.entries(alert.evidence || {}).map(([k, v]) => (
                      <span key={k} className="font-mono">
                        {k}:{' '}
                        <strong className="font-semibold text-slate-900 dark:text-slate-100">
                          {typeof v === 'string' ? v : JSON.stringify(v)}
                        </strong>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Link
                    href={`/runs/${encodeURIComponent(alert.run_id)}`}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650] transition-colors whitespace-nowrap"
                  >
                    <span>Inspect Run</span>
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </Link>
                  <button
                    type="button"
                    onClick={() => void handleAcknowledge(alert.alert_id)}
                    className="inline-flex items-center gap-1.5 rounded-md bg-[#041533] dark:bg-[#0257D5] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#0257D5] dark:hover:bg-[#0346B0] transition-colors whitespace-nowrap"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Acknowledge</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section aria-label="Registered Agents" className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Registered Agents ({agents.length})
        </h3>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-36 rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] animate-pulse"
              />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-center text-xs text-slate-500 dark:text-slate-400">
            No agents registered yet. Launch a simulation scenario or post telemetry events to register agents.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agents.map((agent) => {
              const slo = sloByAgent.get(agent.agent_id);
              return (
                <button
                  key={agent.agent_id}
                  type="button"
                  onClick={() => setSelectedAgent(agent)}
                  className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4 text-left hover:border-[#0257D5] dark:hover:border-[#00C2FF] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0257D5] dark:focus-visible:ring-[#00C2FF]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            'h-2 w-2 rounded-full shrink-0',
                            agent.health_status === 'ACTIVE'
                              ? 'bg-emerald-600 dark:bg-emerald-400'
                              : agent.health_status === 'IDLE'
                                ? 'bg-amber-500'
                                : 'bg-slate-400 dark:bg-slate-600',
                          )}
                          aria-hidden="true"
                        />
                        <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                          {agent.display_name}
                        </h4>
                      </div>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 truncate">
                        <span className="font-mono text-slate-700 dark:text-slate-300">
                          {agent.agent_id}
                        </span>
                        <span aria-hidden="true"> · </span>
                        <span>{agent.framework}</span>
                        <span aria-hidden="true"> · </span>
                        <span>{agent.team}</span>
                        <span aria-hidden="true"> · </span>
                        <span>{agent.environment}</span>
                      </p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {slo && slo.anomaly_count > 0 && (
                        <span className="rounded border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-red-800 dark:text-red-300 tabular-nums">
                          {slo.anomaly_count} alerts
                        </span>
                      )}
                      <StatusBadge status={agent.health_status} compact />
                    </div>
                  </div>

                  {slo && (
                    <div className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-100 dark:border-[#172E56] pt-3 text-xs">
                      <div>
                        <p className="text-slate-500 dark:text-slate-400">Success Rate</p>
                        <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                          {slo.success_rate_pct.toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-500 dark:text-slate-400">p50 / p95</p>
                        <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                          {formatDurationMs(slo.p50_duration_ms)} /{' '}
                          {formatDurationMs(slo.p95_duration_ms)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-500 dark:text-slate-400">Invocations</p>
                        <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                          {formatTokens(slo.total_invocations)}
                        </p>
                      </div>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section aria-label="Recent Execution Runs" className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Recent Execution Runs ({runs.length})
        </h3>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#0A1B3B] text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Root Agent</th>
                <th className="px-4 py-3">Team</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Duration</th>
                <th className="px-4 py-3 text-right">Tokens</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">Started</th>
                <th className="px-4 py-3 text-right">Trace</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#15284B] text-xs">
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    No execution runs recorded yet. Launch a simulation scenario to begin tracing.
                  </td>
                </tr>
              ) : (
                runs.map((run) => {
                  const durationMs = computeRunDurationMs(run.started_at, run.ended_at);
                  const rootLabel =
                    (run.root_agent_id && agentNameMap.get(run.root_agent_id)) ||
                    run.root_agent_id ||
                    '—';

                  return (
                    <tr
                      key={run.run_id}
                      onClick={() =>
                        router.push(`/runs/${encodeURIComponent(run.run_id)}`)
                      }
                      className="cursor-pointer hover:bg-slate-50 dark:hover:bg-[#0D2247] transition-colors"
                    >
                      <td className="px-4 py-3 font-mono font-medium text-[#0257D5] dark:text-[#38BDF8] whitespace-nowrap">
                        {run.run_id}
                      </td>
                      <td className="px-4 py-3 text-slate-900 dark:text-slate-100">
                        <span className="font-medium block">{rootLabel}</span>
                        {run.root_agent_id && (
                          <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                            {run.root_agent_id}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-300 whitespace-nowrap">
                        {run.team}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <StatusBadge status={String(run.status)} compact />
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300 whitespace-nowrap">
                        {run.status === 'RUNNING' || run.status === 'AWAITING_APPROVAL'
                          ? 'live'
                          : formatDurationMs(durationMs)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300 whitespace-nowrap">
                        {formatTokens(run.total_tokens)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums font-medium text-slate-900 dark:text-slate-100 whitespace-nowrap">
                        {formatUsd(run.total_cost_usd)}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {formatRelativeTime(run.started_at)}
                      </td>
                      <td
                        className="px-4 py-3 text-right whitespace-nowrap"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Link
                          href={`/runs/${encodeURIComponent(run.run_id)}`}
                          className="inline-flex items-center gap-1 font-medium text-[#0257D5] dark:text-[#38BDF8] hover:underline"
                        >
                          <span>View</span>
                          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      <AgentProfileModal
        agent={selectedAgent}
        slo={selectedAgent ? sloByAgent.get(selectedAgent.agent_id) : null}
        recentRuns={runs}
        isOpen={Boolean(selectedAgent)}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  );
}
