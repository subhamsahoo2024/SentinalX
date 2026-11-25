'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import { Check, Copy, ExternalLink, X } from 'lucide-react';
import { StatusBadge } from '@/components/StatusBadge';
import { formatDurationMs, formatRelativeTime, formatTokens } from '@/lib/format';
import { useIsClient } from '@/hooks/use-is-client';
import type { AgentResponse, AgentSloDTO, RunListItemResponse } from '@/types/telemetry';

interface AgentProfileModalProps {
  agent: AgentResponse | null;
  slo?: AgentSloDTO | null;
  recentRuns?: RunListItemResponse[];
  isOpen: boolean;
  onClose: () => void;
}

export function AgentProfileModal({
  agent,
  slo,
  recentRuns = [],
  isOpen,
  onClose,
}: AgentProfileModalProps) {
  const mounted = useIsClient();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!mounted || !isOpen || !agent) {
    return null;
  }

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(agent.agent_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore clipboard errors
    }
  };

  const filteredRuns = recentRuns
    .filter((r) => r.root_agent_id === agent.agent_id)
    .slice(0, 5);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-profile-title"
        className="w-full max-w-2xl rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#D4E2F4] dark:border-[#172E56] px-6 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2
                id="agent-profile-title"
                className="text-lg font-semibold text-[#061838] dark:text-slate-100"
              >
                {agent.display_name}
              </h2>
              <StatusBadge status={agent.health_status} compact />
            </div>
            <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
              <button
                type="button"
                onClick={() => void handleCopyId()}
                className="inline-flex items-center gap-1 font-mono text-slate-700 dark:text-slate-200 hover:text-[#0257D5] dark:hover:text-[#00C2FF]"
                title="Copy Agent ID"
              >
                <span>{agent.agent_id}</span>
                {copied ? (
                  <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                ) : (
                  <Copy className="h-3 w-3 text-slate-400" aria-hidden="true" />
                )}
              </button>
              <span aria-hidden="true">·</span>
              <span>{agent.framework}</span>
              <span aria-hidden="true">·</span>
              <span>Team {agent.team}</span>
              <span aria-hidden="true">·</span>
              <span>{agent.environment}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
            aria-label="Close agent profile"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-6 max-h-[78vh] overflow-y-auto">
          {slo && (
            <section>
              <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-3">
                Service Level Objectives
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 border border-[#D4E2F4] dark:border-[#172E56] rounded-md p-4 bg-[#F5F9FF] dark:bg-[#0A1B3B]">
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Success Rate</p>
                  <p className="mt-1 text-lg font-semibold font-mono tabular-nums text-[#061838] dark:text-slate-100">
                    {slo.success_rate_pct.toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">p50 / p95 Latency</p>
                  <p className="mt-1 text-sm font-semibold font-mono tabular-nums text-[#061838] dark:text-slate-100">
                    {formatDurationMs(slo.p50_duration_ms)} /{' '}
                    {formatDurationMs(slo.p95_duration_ms)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Avg Tokens / Call</p>
                  <p className="mt-1 text-lg font-semibold font-mono tabular-nums text-[#061838] dark:text-slate-100">
                    {formatTokens(slo.avg_tokens_per_call)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Invocations / Anomalies</p>
                  <p className="mt-1 text-sm font-semibold font-mono tabular-nums text-[#061838] dark:text-slate-100">
                    {formatTokens(slo.total_invocations)} /{' '}
                    <span
                      className={
                        slo.anomaly_count > 0
                          ? 'text-red-700 dark:text-red-400'
                          : 'text-slate-700 dark:text-slate-300'
                      }
                    >
                      {slo.anomaly_count}
                    </span>
                  </p>
                </div>
              </div>
            </section>
          )}

          <section className="grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-[#D4E2F4] dark:border-[#172E56] pt-5 text-xs">
            <div>
              <p className="text-slate-500 dark:text-slate-400">Registration Status</p>
              <p className="mt-1 font-medium text-[#061838] dark:text-slate-100">{agent.status}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Active Runs</p>
              <p className="mt-1 font-mono tabular-nums font-medium text-[#061838] dark:text-slate-100">
                {agent.active_runs_count}
              </p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Last Heartbeat</p>
              <p className="mt-1 font-medium text-[#061838] dark:text-slate-100">
                {formatRelativeTime(agent.last_seen_at)}
              </p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Declared Tools</p>
              <p className="mt-1 font-mono tabular-nums font-medium text-[#061838] dark:text-slate-100">
                {agent.declared_tools.length}
              </p>
            </div>
          </section>

          <section className="border-t border-[#D4E2F4] dark:border-[#172E56] pt-5">
            <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2.5">
              Declared Tool Capabilities
            </h3>
            {agent.declared_tools.length === 0 ? (
              <p className="text-xs text-slate-500 dark:text-slate-400">No declared tools registered.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {agent.declared_tools.map((tool, i) => (
                  <span
                    key={`${String(tool)}-${i}`}
                    className="rounded border border-[#D4E2F4] dark:border-[#1D3868] bg-[#F5F9FF] dark:bg-[#0A1B3B] px-2.5 py-1 font-mono text-xs text-[#061838] dark:text-slate-200"
                  >
                    {typeof tool === 'string' ? tool : JSON.stringify(tool)}
                  </span>
                ))}
              </div>
            )}
          </section>

          <section className="border-t border-[#D4E2F4] dark:border-[#172E56] pt-5">
            <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2.5">
              Recent Invocations
            </h3>
            {filteredRuns.length === 0 ? (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                No recent root runs recorded for this agent.
              </p>
            ) : (
              <div className="divide-y divide-[#D4E2F4] dark:divide-[#172E56] border border-[#D4E2F4] dark:border-[#172E56] rounded-md">
                {filteredRuns.map((run) => (
                  <Link
                    key={run.run_id}
                    href={`/runs/${encodeURIComponent(run.run_id)}`}
                    onClick={onClose}
                    className="flex items-center justify-between gap-3 px-3.5 py-2.5 text-xs hover:bg-[#F5F9FF] dark:hover:bg-[#0D2247] transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono font-medium text-[#0257D5] dark:text-[#38BDF8] truncate">
                        {run.run_id}
                      </span>
                      <StatusBadge status={run.status} compact />
                    </div>
                    <div className="flex items-center gap-3 text-slate-500 dark:text-slate-400 font-mono tabular-nums shrink-0">
                      <span>{formatTokens(run.total_tokens)} tok</span>
                      <span>{formatRelativeTime(run.started_at)}</span>
                      <ExternalLink className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>,
    document.body,
  );
}
