'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  ShieldX,
} from 'lucide-react';
import { useApprovals } from '@/components/governance/ApprovalContext';
import { StatusBadge } from '@/components/StatusBadge';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import {
  fetchApprovals,
  fetchAuditEvents,
  submitApprovalDecision,
  verifyAuditChain,
} from '@/lib/api';
import { getStoredUser } from '@/lib/auth';
import { formatRelativeTime, formatUtcTimestamp } from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  ActorRole,
  ApprovalDTO,
  AuditChainVerificationDTO,
  AuditEventDTO,
  WebSocketMessage,
} from '@/types/telemetry';

const STATUS_TABS = ['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as const;
type StatusTab = (typeof STATUS_TABS)[number];

export default function ApprovalsPage() {
  const { refreshPending } = useApprovals();
  const [statusFilter, setStatusFilter] = useState<StatusTab>('ALL');
  const [allApprovals, setAllApprovals] = useState<ApprovalDTO[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventDTO[]>([]);
  const [chainStatus, setChainStatus] = useState<AuditChainVerificationDTO | null>(null);
  const [expandedArgs, setExpandedArgs] = useState<Record<string, boolean>>({});
  const [expandedPayloads, setExpandedPayloads] = useState<Record<string, boolean>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [roles, setRoles] = useState<Record<string, ActorRole>>({});
  const [errorsByApproval, setErrorsByApproval] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadData = useCallback(async () => {
    try {
      const [approvalsData, auditData, verification] = await Promise.all([
        fetchApprovals(),
        fetchAuditEvents(),
        verifyAuditChain().catch((err) => {
          console.warn('Failed to verify audit chain:', err);
          return null;
        }),
      ]);
      setAllApprovals(approvalsData);
      setAuditEvents(auditData);
      if (verification) setChainStatus(verification);
    } catch (err) {
      console.error('Failed to load governance data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleWsMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (
        msg.type === 'APPROVAL_REQUIRED' ||
        msg.type === 'APPROVAL_DECIDED' ||
        msg.type === 'FLEET_UPDATED'
      ) {
        void loadData();
      }
    },
    [loadData],
  );

  useWebSocketStream<WebSocketMessage>('/ws/fleet', handleWsMessage);

  const visibleApprovals = useMemo(() => {
    if (statusFilter === 'ALL') return allApprovals;
    return allApprovals.filter((a) => a.status === statusFilter);
  }, [allApprovals, statusFilter]);

  const counts = useMemo(() => {
    return {
      pending: allApprovals.filter((a) => a.status === 'PENDING').length,
      approved: allApprovals.filter((a) => a.status === 'APPROVED').length,
      rejected: allApprovals.filter((a) => a.status === 'REJECTED').length,
      audits: chainStatus?.total_events ?? auditEvents.length,
    };
  }, [allApprovals, auditEvents.length, chainStatus]);

  const defaultRole: ActorRole = (() => {
    const r = getStoredUser()?.role;
    if (r === 'approver' || r === 'admin' || r === 'operator' || r === 'viewer') return r;
    return 'approver';
  })();

  const handleDecision = async (approvalId: string, decision: 'APPROVED' | 'REJECTED') => {
    setBusyId(approvalId);
    setErrorsByApproval((prev) => {
      const next = { ...prev };
      delete next[approvalId];
      return next;
    });
    try {
      const selectedRole = roles[approvalId] ?? defaultRole;
      const actorId = getStoredUser()?.email || `${selectedRole}@sentinel.local`;
      await submitApprovalDecision(
        approvalId,
        decision,
        comments[approvalId] ?? '',
        selectedRole,
        actorId,
      );
      await Promise.all([loadData(), refreshPending()]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorsByApproval((prev) => ({ ...prev, [approvalId]: msg }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
          Human-in-the-Loop Approvals & Audit Ledger
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Review blocked high-risk tool invocations and verify the SHA-256 tamper-evident audit chain.
        </p>
      </div>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Pending Gates</p>
            {counts.pending > 0 && (
              <span
                className="h-2 w-2 rounded-full bg-amber-500 animate-pulse"
                aria-hidden="true"
              />
            )}
          </div>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-amber-700 dark:text-amber-400">
            {counts.pending}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Approved Actions</p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-emerald-700 dark:text-emerald-400">
            {counts.approved}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Rejected Actions</p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-red-700 dark:text-red-400">
            {counts.rejected}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Audit Log Entries</p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-slate-900 dark:text-slate-100">
            {counts.audits}
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Runtime Approval Gates
          </h3>
          <div className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-[#0A1B3B] border border-transparent dark:border-[#172E56] p-1">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setStatusFilter(tab)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap',
                  statusFilter === tab
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0257D5] dark:text-white'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
                )}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-center text-xs text-slate-500 dark:text-slate-400">
            Loading approval requests...
          </div>
        ) : visibleApprovals.length === 0 ? (
          <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-center text-xs text-slate-500 dark:text-slate-400">
            No approvals matching filter {statusFilter}.
          </div>
        ) : (
          <div className="space-y-4">
            {visibleApprovals.map((item) => {
              const argsOpen = Boolean(expandedArgs[item.approval_id]);
              const activeRole = roles[item.approval_id] ?? defaultRole;
              const isPending = item.status === 'PENDING';
              const approvalError = errorsByApproval[item.approval_id];

              return (
                <article
                  key={item.approval_id}
                  className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-5 space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <StatusBadge status={item.status} compact />
                        <StatusBadge status={item.risk_level} compact />
                        <h4 className="text-sm font-semibold font-mono text-slate-900 dark:text-slate-100">
                          {item.tool_name}
                        </h4>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
                        {item.approval_id} · {item.agent_id} · Span {item.span_id} ·{' '}
                        {formatRelativeTime(item.created_at)}
                      </p>
                    </div>

                    <Link
                      href={`/runs/${encodeURIComponent(item.run_id)}`}
                      className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-[#0257D5] dark:text-[#38BDF8] hover:bg-[#EFF6FF] dark:hover:bg-[#102650] transition-colors shrink-0 whitespace-nowrap"
                    >
                      <span>{item.run_id}</span>
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </Link>
                  </div>

                  <p className="text-xs text-slate-700 dark:text-slate-200 bg-slate-50 dark:bg-[#0A1B3B] border border-slate-200 dark:border-[#172E56] rounded-md px-3.5 py-2.5">
                    {item.policy_reason}
                  </p>

                  <div>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedArgs((prev) => ({
                          ...prev,
                          [item.approval_id]: !argsOpen,
                        }))
                      }
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white"
                    >
                      {argsOpen ? (
                        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                      )}
                      <span>Sanitized Arguments JSON</span>
                    </button>

                    {argsOpen && (
                      <pre className="mt-2 rounded-md border border-slate-200 dark:border-[#172E56] bg-[#040B18] p-3 text-xs font-mono text-slate-100 overflow-x-auto">
                        {JSON.stringify(item.sanitized_args, null, 2)}
                      </pre>
                    )}
                  </div>

                  {isPending ? (
                    <div className="border-t border-slate-200 dark:border-[#172E56] pt-4 space-y-3">
                      {approvalError && (
                        <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2.5 text-xs font-mono text-red-700 dark:text-red-300 flex items-center gap-2">
                          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                          <span>{approvalError}</span>
                        </div>
                      )}
                      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 flex-1">
                          <div>
                            <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                              Actor Role
                            </label>
                            <select
                              value={activeRole}
                              onChange={(e) =>
                                setRoles((prev) => ({
                                  ...prev,
                                  [item.approval_id]: e.target.value as ActorRole,
                                }))
                              }
                              className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1.5 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                            >
                              <option value="approver">approver</option>
                              <option value="admin">admin</option>
                              <option value="operator">operator</option>
                              <option value="viewer">viewer</option>
                            </select>
                          </div>
                          <div className="sm:col-span-2">
                            <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                              Review Justification
                            </label>
                            <input
                              type="text"
                              value={comments[item.approval_id] ?? ''}
                              onChange={(e) =>
                                setComments((prev) => ({
                                  ...prev,
                                  [item.approval_id]: e.target.value,
                                }))
                              }
                              placeholder="Enter rationale for audit ledger..."
                              className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                            />
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            disabled={busyId === item.approval_id}
                            onClick={() => void handleDecision(item.approval_id, 'REJECTED')}
                            className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 px-3.5 py-2 text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/60 disabled:opacity-50 transition-colors whitespace-nowrap"
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            disabled={busyId === item.approval_id}
                            onClick={() => void handleDecision(item.approval_id, 'APPROVED')}
                            className="rounded-md bg-emerald-700 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50 transition-colors whitespace-nowrap"
                          >
                            Approve
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="border-t border-slate-200 dark:border-[#172E56] pt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600 dark:text-slate-400">
                      <span>
                        Decided by{' '}
                        <strong className="font-medium text-slate-900 dark:text-slate-100">
                          {item.decided_by || 'System'}
                        </strong>{' '}
                        · {formatRelativeTime(item.decided_at)}
                      </span>
                      {item.comment && (
                        <span className="italic text-slate-600 dark:text-slate-400">
                          &ldquo;{item.comment}&rdquo;
                        </span>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Immutable Governance Audit Log
        </h3>

        {chainStatus && (
          <div
            className={cn(
              'rounded-lg border px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs',
              chainStatus.valid
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800/80 dark:bg-emerald-950/50 dark:text-emerald-200'
                : 'border-red-200 bg-red-50 text-red-900 dark:border-red-800/80 dark:bg-red-950/50 dark:text-red-200',
            )}
          >
            <div className="flex items-center gap-2 font-medium">
              {chainStatus.valid ? (
                <ShieldCheck className="h-4 w-4 text-emerald-700 dark:text-emerald-400 shrink-0" aria-hidden="true" />
              ) : (
                <ShieldX className="h-4 w-4 text-red-700 dark:text-red-400 shrink-0" aria-hidden="true" />
              )}
              <span>
                {chainStatus.valid
                  ? 'SHA-256 Hash Chain Verified Intact'
                  : `Hash Chain Broken at ${chainStatus.broken_at_audit_id}`}
              </span>
            </div>
            <div className="font-mono text-[11px] tabular-nums">
              Records: {chainStatus.total_events} · Latest:{' '}
              {chainStatus.latest_hash ? chainStatus.latest_hash.slice(0, 14) : '—'}
            </div>
          </div>
        )}

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#0A1B3B] text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Target ID</th>
                <th className="px-4 py-3">Entry Hash</th>
                <th className="px-4 py-3 text-right">Payload</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#15284B] text-xs">
              {auditEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    No audit events recorded yet.
                  </td>
                </tr>
              ) : (
                auditEvents.map((ev) => {
                  const isOpen = Boolean(expandedPayloads[ev.audit_id]);
                  return (
                    <tr key={ev.audit_id} className="align-top">
                      <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap">
                        {formatUtcTimestamp(ev.created_at)}
                      </td>
                      <td className="px-4 py-3 font-mono font-semibold text-slate-900 dark:text-slate-100 whitespace-nowrap">
                        {ev.action}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-700 dark:text-slate-300 whitespace-nowrap">
                        {ev.actor_id}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="rounded border border-slate-200 dark:border-[#1D3868] bg-slate-50 dark:bg-[#0A1B3B] px-2 py-0.5 font-mono text-[11px] text-slate-700 dark:text-slate-200">
                          {ev.actor_role}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-700 dark:text-slate-300 whitespace-nowrap">
                        {ev.target_id}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {ev.entry_hash ? ev.entry_hash.slice(0, 10) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedPayloads((prev) => ({
                              ...prev,
                              [ev.audit_id]: !isOpen,
                            }))
                          }
                          className="font-medium text-[#0257D5] dark:text-[#38BDF8] hover:underline whitespace-nowrap"
                        >
                          {isOpen ? 'Hide' : 'Inspect'}
                        </button>
                        {isOpen && (
                          <pre className="mt-2 text-left rounded border border-slate-200 dark:border-[#172E56] bg-[#040B18] p-2.5 text-[11px] font-mono text-slate-100 overflow-x-auto max-w-xs ml-auto">
                            {JSON.stringify(ev.payload, null, 2)}
                          </pre>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
