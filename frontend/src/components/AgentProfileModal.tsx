'use client';

import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import {
  Activity,
  ArrowUpRight,
  Bot,
  Check,
  Coins,
  Copy,
  Layers,
  ShieldCheck,
  Wrench,
  X,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { AgentResponse, AgentSloDTO, RunListItemResponse } from '@/types/telemetry';

export interface AgentProfileModalProps {
  agent: AgentResponse | null;
  slo?: AgentSloDTO | null;
  recentRuns?: RunListItemResponse[];
  isOpen: boolean;
  onClose: () => void;
}

const subscribeNoop = () => () => {};

function formatLatency(ms?: number | null): string {
  if (ms === undefined || ms === null || isNaN(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

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

export function AgentProfileModal({
  agent,
  slo,
  recentRuns = [],
  isOpen,
  onClose,
}: AgentProfileModalProps) {
  const isMounted = useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false
  );

  const [copiedId, setCopiedId] = useState(false);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  const handleCopyId = () => {
    if (!agent) return;
    navigator.clipboard.writeText(agent.agent_id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  if (!isMounted || !isOpen || !agent) {
    return null;
  }

  const isHealthy = agent.health_status === 'ACTIVE';
  const isIdle = agent.health_status === 'IDLE';

  const successRate = slo ? slo.success_rate_pct : 100.0;
  const successRateClass =
    successRate >= 95
      ? 'text-emerald-400'
      : successRate >= 80
      ? 'text-amber-400'
      : 'text-rose-400';

  const modalContent = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[90vh] shadow-2xl flex flex-col overflow-hidden text-slate-100 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="p-6 border-b border-slate-800 flex items-start justify-between gap-4 bg-slate-900/90 shrink-0">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 shadow-inner">
              <Bot className="w-6 h-6" />
            </div>

            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-lg font-bold text-slate-100 tracking-tight truncate">
                  {agent.display_name}
                </h3>

                {/* Health Status Indicator */}
                <span
                  className={cn(
                    'px-2 py-0.5 rounded text-[11px] font-mono font-bold border flex items-center gap-1.5 shrink-0 uppercase tracking-wider',
                    isHealthy
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                      : isIdle
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  )}
                >
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      isHealthy
                        ? 'bg-emerald-400 animate-pulse'
                        : isIdle
                        ? 'bg-amber-400'
                        : 'bg-slate-500'
                    )}
                  />
                  {agent.health_status}
                </span>
              </div>

              {/* Agent ID & Copy Button */}
              <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                <span>ID:</span>
                <button
                  type="button"
                  onClick={handleCopyId}
                  className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors"
                  title="Click to copy Agent ID"
                >
                  <span className="truncate max-w-[280px]">{agent.agent_id}</span>
                  {copiedId ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : (
                    <Copy className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300 shrink-0" />
                  )}
                </button>
              </div>

              {/* Tag Badges */}
              <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                  {agent.framework || 'custom'}
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/80 text-slate-300 border border-slate-700/60">
                  team: {agent.team || 'default'}
                </span>
                {agent.environment && (
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/50 text-slate-400 border border-slate-700/40">
                    env: {agent.environment}
                  </span>
                )}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors shrink-0"
            title="Close Profile (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-xs">
          {/* Section 1: SLO Performance Telemetry */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2 text-slate-300 font-semibold uppercase tracking-wider text-[11px]">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Service Level Objectives (SLO) Performance</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {/* Metric 1: Success Rate */}
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                  Success Rate
                </span>
                <div className="mt-1.5">
                  <span className={cn('text-xl font-bold font-mono', successRateClass)}>
                    {slo ? `${slo.success_rate_pct.toFixed(1)}%` : '100.0%'}
                  </span>
                  <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                    {slo ? `${slo.succeeded_count} succ / ${slo.failed_count} fail` : 'No runs'}
                  </div>
                </div>
              </div>

              {/* Metric 2: Latency Percentiles */}
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                  p50 / p95 Latency
                </span>
                <div className="mt-1.5">
                  <span className="text-sm font-bold font-mono text-slate-200">
                    {formatLatency(slo?.p50_duration_ms)} / {formatLatency(slo?.p95_duration_ms)}
                  </span>
                  <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                    Median & 95th %ile
                  </div>
                </div>
              </div>

              {/* Metric 3: Avg Tokens / Call */}
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                  Avg Tokens / Call
                </span>
                <div className="mt-1.5">
                  <span className="text-xl font-bold font-mono text-amber-300">
                    {slo ? Math.round(slo.avg_tokens_per_call).toLocaleString() : '0'}
                  </span>
                  <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                    Tokens consumed
                  </div>
                </div>
              </div>

              {/* Metric 4: Invocations & Anomalies */}
              <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col justify-between">
                <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                  Invocations
                </span>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  <span className="text-xl font-bold font-mono text-slate-100">
                    {slo ? slo.total_invocations : 0}
                  </span>
                  {slo && slo.anomaly_count > 0 && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                      {slo.anomaly_count} alert{slo.anomaly_count > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                  {slo && slo.anomaly_count > 0 ? 'Anomalies detected' : 'Zero anomalies'}
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Runtime Properties */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2 text-slate-300 font-semibold uppercase tracking-wider text-[11px]">
              <Activity className="w-4 h-4 text-indigo-400" />
              <span>Runtime Information</span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-800/60">
                <span className="text-slate-400">Status:</span>
                <span className="font-semibold text-slate-200 uppercase">{agent.status}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-800/60">
                <span className="text-slate-400">Active In-Flight Runs:</span>
                <span className="font-semibold text-cyan-300">{agent.active_runs_count}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-800/60">
                <span className="text-slate-400">Last Seen:</span>
                <span className="font-medium text-slate-300" title={agent.last_seen_at}>
                  {formatRelativeTime(agent.last_seen_at)}
                </span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-800/60">
                <span className="text-slate-400">Registered Tools:</span>
                <span className="font-semibold text-slate-200">
                  {agent.declared_tools?.length || 0} tools
                </span>
              </div>
            </div>
          </div>

          {/* Section 3: Declared Tools & Capabilities */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-300 font-semibold uppercase tracking-wider text-[11px]">
                <Wrench className="w-4 h-4 text-emerald-400" />
                <span>Declared Tools & Capabilities</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                {agent.declared_tools?.length || 0}
              </span>
            </div>

            {agent.declared_tools && agent.declared_tools.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {agent.declared_tools.map((tool, idx) => {
                  const toolName =
                    typeof tool === 'string'
                      ? tool
                      : typeof tool === 'object' && tool !== null && 'name' in tool
                      ? String(tool.name)
                      : JSON.stringify(tool);

                  return (
                    <div
                      key={idx}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950/60 border border-slate-800 font-mono text-xs text-slate-300 shadow-sm"
                    >
                      <Wrench className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      <span className="font-medium">{toolName}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-slate-500 font-mono text-xs italic">
                No static tools explicitly registered for this agent. Capabilities may be dispatched dynamically at runtime.
              </div>
            )}
          </div>

          {/* Section 4: Recent Execution Runs */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-300 font-semibold uppercase tracking-wider text-[11px]">
                <Layers className="w-4 h-4 text-cyan-400" />
                <span>Recent Invocations & Runs</span>
              </div>
              {recentRuns.length > 0 && (
                <span className="text-[11px] font-mono text-slate-500">
                  Showing latest {Math.min(5, recentRuns.length)}
                </span>
              )}
            </div>

            {recentRuns.length > 0 ? (
              <div className="divide-y divide-slate-800/60 rounded-xl border border-slate-800 bg-slate-950/40 overflow-hidden font-mono">
                {recentRuns.slice(0, 5).map((run) => (
                  <div
                    key={run.run_id}
                    className="p-3 flex items-center justify-between gap-3 hover:bg-slate-900/60 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Link
                        href={`/runs/${encodeURIComponent(run.run_id)}`}
                        onClick={onClose}
                        className="font-bold text-cyan-400 hover:text-cyan-300 transition-colors truncate flex items-center gap-1 group"
                        title="Open Run Detail View"
                      >
                        <span className="truncate">{run.run_id}</span>
                        <ArrowUpRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform shrink-0" />
                      </Link>

                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-[10px] font-semibold border uppercase tracking-wider shrink-0',
                          run.status === 'SUCCEEDED'
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                            : run.status === 'FAILED' || run.status === 'TIMED_OUT'
                            ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                            : run.status === 'RUNNING'
                            ? 'bg-sky-500/20 text-sky-300 border-sky-500/40 animate-pulse'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        )}
                      >
                        {run.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-slate-400 text-xs shrink-0">
                      <div className="flex items-center gap-1">
                        <Coins className="w-3.5 h-3.5 text-amber-400" />
                        <span>{(run.total_tokens || 0).toLocaleString()}</span>
                      </div>
                      <span className="text-slate-500">{formatRelativeTime(run.started_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-slate-500 font-mono text-xs italic">
                No recent runs found where this agent was the root delegator.
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between gap-3 shrink-0 font-mono text-xs">
          <span className="text-slate-500">
            Sentinel-X Agent Observability Control Tower
          </span>

          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold transition-colors border border-slate-700/60"
          >
            Close Profile
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}

