'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Maximize2,
  Minimize2,
  ShieldAlert,
} from 'lucide-react';
import { useApprovals } from '@/components/governance/ApprovalContext';
import { StatusBadge } from '@/components/StatusBadge';
import { formatRelativeTime } from '@/lib/format';
import { AUTH_CHANGED_EVENT, getStoredUser, SentinelUser } from '@/lib/auth';
import type { ActorRole } from '@/types/telemetry';

export function ApprovalModal() {
  const { pendingApprovals, decideApproval } = useApprovals();
  const [activeIndex, setActiveIndex] = useState(0);
  const [minimized, setMinimized] = useState(false);
  const [comment, setComment] = useState('');
  const [currentUser, setCurrentUser] = useState<SentinelUser | null>(null);
  const [role, setRole] = useState<ActorRole>('approver');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const syncUser = () => setCurrentUser(getStoredUser());
    syncUser();
    window.addEventListener(AUTH_CHANGED_EVENT, syncUser);
    window.addEventListener('storage', syncUser);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, syncUser);
      window.removeEventListener('storage', syncUser);
    };
  }, []);

  if (pendingApprovals.length === 0) {
    return null;
  }

  const safeIndex = Math.min(activeIndex, pendingApprovals.length - 1);
  const current = pendingApprovals[safeIndex];
  const effectiveRole = currentUser ? (currentUser.role as ActorRole) : role;

  const handleDecision = async (decision: 'APPROVED' | 'REJECTED') => {
    if (!current || submitting) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      await decideApproval(current.approval_id, decision, comment, effectiveRole);
      setComment('');
      setActiveIndex(0);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside
      key="global-hitl-modal"
      aria-label="Pre-Execution Governance Gate"
      className="animate-slide-up fixed bottom-4 right-4 z-40 w-[420px] max-w-[calc(100vw-2rem)] rounded-lg border border-amber-300 dark:border-amber-700/80 bg-white dark:bg-[#07152E] shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] bg-amber-50/80 dark:bg-amber-950/50 px-4 py-2.5 rounded-t-lg">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldAlert className="h-4 w-4 text-amber-700 dark:text-amber-400 shrink-0" aria-hidden="true" />
          <span className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">
            Approval Gate Required ({pendingApprovals.length})
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {pendingApprovals.length > 1 && (
            <>
              <button
                type="button"
                onClick={() =>
                  setActiveIndex(
                    (safeIndex - 1 + pendingApprovals.length) % pendingApprovals.length,
                  )
                }
                className="rounded p-1 text-slate-600 dark:text-slate-300 hover:bg-amber-100 dark:hover:bg-amber-900/40"
                aria-label="Previous pending approval"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <span className="text-[11px] font-mono tabular-nums text-slate-600 dark:text-slate-300 px-1">
                {safeIndex + 1}/{pendingApprovals.length}
              </span>
              <button
                type="button"
                onClick={() => setActiveIndex((safeIndex + 1) % pendingApprovals.length)}
                className="rounded p-1 text-slate-600 dark:text-slate-300 hover:bg-amber-100 dark:hover:bg-amber-900/40"
                aria-label="Next pending approval"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setMinimized((m) => !m)}
            className="rounded p-1 text-slate-600 dark:text-slate-300 hover:bg-amber-100 dark:hover:bg-amber-900/40"
            aria-label={minimized ? 'Maximize approval dialog' : 'Minimize approval dialog'}
          >
            {minimized ? (
              <Maximize2 className="h-3.5 w-3.5" />
            ) : (
              <Minimize2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {minimized ? (
        <div className="flex items-center justify-between px-4 py-2.5 text-xs">
          <span className="font-mono font-medium text-slate-900 dark:text-slate-100 truncate">
            {current.tool_name}
          </span>
          <StatusBadge status={current.risk_level} compact />
        </div>
      ) : (
        <div className="p-4 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold font-mono text-slate-900 dark:text-slate-100 truncate">
                {current.tool_name}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {current.agent_id} · {formatRelativeTime(current.created_at)}
              </p>
            </div>
            <StatusBadge status={current.risk_level} compact />
          </div>

          <p className="text-xs text-slate-700 dark:text-slate-200 leading-relaxed bg-slate-50 dark:bg-[#0A1B3B] border border-slate-200 dark:border-[#172E56] rounded-md p-2.5">
            {current.policy_reason}
          </p>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 dark:text-slate-400">
            <span className="truncate">Span: {current.span_id}</span>
            <Link
              href={`/runs/${encodeURIComponent(current.run_id)}`}
              className="inline-flex items-center gap-1 text-[#0257D5] dark:text-[#38BDF8] hover:underline shrink-0"
            >
              <span>{current.run_id}</span>
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </Link>
          </div>

          <div>
            <p className="text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
              Sanitized Arguments
            </p>
            <pre className="max-h-24 overflow-auto rounded-md border border-slate-200 dark:border-[#172E56] bg-[#040B18] p-2.5 text-[11px] font-mono text-slate-100">
              {JSON.stringify(current.sanitized_args, null, 2)}
            </pre>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-1">
              <label
                htmlFor="modal-actor-role"
                className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1"
              >
                {currentUser ? 'Auth Role' : 'Actor Role'}
              </label>
              {currentUser ? (
                <div className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-slate-50 dark:bg-[#0A1B3B] px-2 py-1.5 text-xs font-mono text-slate-900 dark:text-slate-100 truncate">
                  {currentUser.role}
                </div>
              ) : (
                <select
                  id="modal-actor-role"
                  value={role}
                  onChange={(e) => {
                    setRole(e.target.value as ActorRole);
                    setErrorMessage(null);
                  }}
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2 py-1.5 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                >
                  <option value="approver">approver</option>
                  <option value="admin">admin</option>
                  <option value="operator">operator</option>
                  <option value="viewer">viewer</option>
                </select>
              )}
            </div>
            <div className="col-span-2">
              <label
                htmlFor="modal-audit-comment"
                className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1"
              >
                Audit Justification
              </label>
              <input
                id="modal-audit-comment"
                type="text"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Optional review note..."
                className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-2.5 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
              />
            </div>
          </div>

          {errorMessage && (
            <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2 text-[11px] font-mono text-red-700 dark:text-red-300 flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-200 dark:border-[#172E56]">
            <button
              type="button"
              disabled={submitting}
              onClick={() => void handleDecision('REJECTED')}
              className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/60 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              Reject Action
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => void handleDecision('APPROVED')}
              className="rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50 transition-colors whitespace-nowrap"
            >
              Approve Execution
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
