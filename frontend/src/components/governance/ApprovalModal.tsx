'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Minimize2,
  Maximize2,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { useApprovals } from './ApprovalContext';
import { ActorRole } from '@/types/telemetry';

export function ApprovalModal() {
  const { pendingApprovals, decideApproval } = useApprovals();
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [selectedRole, setSelectedRole] = useState<ActorRole>('approver');
  const [comment, setComment] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isMinimized, setIsMinimized] = useState<boolean>(false);

  // If no pending approvals, render nothing
  if (!pendingApprovals || pendingApprovals.length === 0) {
    return null;
  }

  // Ensure current index is valid
  const safeIndex = Math.min(currentIndex, pendingApprovals.length - 1);
  const currentApproval = pendingApprovals[safeIndex] || pendingApprovals[0];

  const handleDecision = async (decision: 'APPROVED' | 'REJECTED') => {
    if (!currentApproval) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await decideApproval(
        currentApproval.approval_id,
        decision,
        comment,
        selectedRole
      );
      setComment('');
      // Adjust index if we were on the last item
      if (currentIndex >= pendingApprovals.length - 1) {
        setCurrentIndex(Math.max(0, pendingApprovals.length - 2));
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isCritical = currentApproval.risk_level?.toUpperCase() === 'CRITICAL';
  const isHigh = currentApproval.risk_level?.toUpperCase() === 'HIGH';

  if (isMinimized) {
    return (
      <div className="fixed bottom-6 right-6 z-50 animate-bounce">
        <button
          onClick={() => setIsMinimized(false)}
          className={`flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-2xl backdrop-blur-md border font-sans text-xs font-semibold tracking-wide transition-all ${
            isCritical
              ? 'bg-rose-950/90 text-rose-200 border-rose-500/50 hover:bg-rose-900/90 shadow-rose-950/60'
              : 'bg-amber-950/90 text-amber-200 border-amber-500/50 hover:bg-amber-900/90 shadow-amber-950/60'
          }`}
        >
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
          <ShieldAlert className="w-4 h-4 text-rose-400" />
          <span>
            {pendingApprovals.length} Pending Approval Gate
            {pendingApprovals.length > 1 ? 's' : ''}
          </span>
          <Maximize2 className="w-3.5 h-3.5 text-slate-400 ml-1" />
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-lg select-text font-sans">
      <div
        className={`rounded-2xl border shadow-2xl backdrop-blur-2xl bg-slate-900/95 overflow-hidden transition-all ${
          isCritical
            ? 'border-rose-500/50 shadow-rose-950/40 ring-1 ring-rose-500/30'
            : isHigh
            ? 'border-amber-500/50 shadow-amber-950/40 ring-1 ring-amber-500/30'
            : 'border-cyan-500/50 shadow-cyan-950/40 ring-1 ring-cyan-500/30'
        }`}
      >
        {/* Top Glowing Status Bar */}
        <div
          className={`h-1.5 w-full ${
            isCritical
              ? 'bg-gradient-to-r from-rose-500 via-red-500 to-amber-500 animate-pulse'
              : 'bg-gradient-to-r from-amber-500 via-orange-500 to-yellow-500'
          }`}
        />

        {/* Modal Header */}
        <div className="px-5 py-3.5 border-b border-slate-800/80 bg-slate-950/40 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div
              className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                isCritical
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
              }`}
            >
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center gap-2">
                Governance Pre-Execution Gate
                {isCritical && (
                  <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                    CRITICAL
                  </span>
                )}
                {!isCritical && (
                  <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    {currentApproval.risk_level || 'HIGH'}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-400 font-mono">
                {currentApproval.approval_id}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Queue Counter if multiple pending */}
            {pendingApprovals.length > 1 && (
              <div className="flex items-center gap-1 bg-slate-800/80 border border-slate-700/80 rounded-md px-1.5 py-0.5 text-[11px] font-mono text-slate-300">
                <button
                  type="button"
                  disabled={safeIndex === 0}
                  onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                  className="p-0.5 hover:text-white disabled:opacity-30 disabled:hover:text-slate-300"
                  title="Previous approval"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <span>
                  {safeIndex + 1}/{pendingApprovals.length}
                </span>
                <button
                  type="button"
                  disabled={safeIndex >= pendingApprovals.length - 1}
                  onClick={() =>
                    setCurrentIndex((prev) =>
                      Math.min(pendingApprovals.length - 1, prev + 1)
                    )
                  }
                  className="p-0.5 hover:text-white disabled:opacity-30 disabled:hover:text-slate-300"
                  title="Next approval"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Minimize button */}
            <button
              type="button"
              onClick={() => setIsMinimized(true)}
              className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
              title="Minimize drawer"
            >
              <Minimize2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Target Tool and Agent Info */}
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">
                  Target Tool:
                </span>
                <code className="px-2 py-0.5 bg-slate-900 border border-cyan-500/30 rounded text-cyan-300 font-mono text-xs font-semibold">
                  {currentApproval.tool_name}
                </code>
              </div>
              <Link
                href={`/runs/${currentApproval.run_id}`}
                className="text-xs font-mono text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 group transition-colors"
              >
                <span>Run: {currentApproval.run_id.slice(0, 14)}...</span>
                <ExternalLink className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>

            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-mono">
              <span className="text-slate-400">Agent:</span>
              <span className="text-slate-200">{currentApproval.agent_id}</span>
              <span className="text-slate-400">•</span>
              <span className="text-slate-400">Span:</span>
              <span className="text-slate-400">{currentApproval.span_id}</span>
            </div>
          </div>

          {/* Policy Reason Callout */}
          <div className="p-3.5 bg-amber-950/30 border border-amber-500/30 rounded-xl flex items-start gap-3 text-xs text-amber-200/95 leading-relaxed">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-amber-300 text-[11px] uppercase tracking-wider mb-0.5">
                Policy Reason
              </div>
              <div>{currentApproval.policy_reason}</div>
            </div>
          </div>

          {/* Formatted JSON Sanitized Arguments */}
          <div className="space-y-1.5">
            <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Sanitized Arguments</span>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.2 rounded">
                PII Redacted
              </span>
            </div>
            <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 font-mono text-xs text-slate-300 max-h-36 overflow-y-auto">
              <pre className="whitespace-pre-wrap break-all leading-snug">
                {JSON.stringify(currentApproval.sanitized_args, null, 2)}
              </pre>
            </div>
          </div>

          {/* RBAC Role Selector & Reviewer Comment */}
          <div className="pt-2 border-t border-slate-800/80 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-center">
              <div>
                <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1">
                  Actor Role (RBAC):
                </label>
                <select
                  value={selectedRole}
                  onChange={(e) => {
                    setSelectedRole(e.target.value as ActorRole);
                    setErrorMessage(null);
                  }}
                  className="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                >
                  <option value="approver">approver (Authorized)</option>
                  <option value="admin">admin (Authorized)</option>
                  <option value="operator">operator (403 Forbidden)</option>
                  <option value="viewer">viewer (403 Forbidden)</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1">
                  Authorization Note:
                </label>
                <input
                  type="text"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Optional review comment..."
                  className="w-full bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-500 transition-colors"
                />
              </div>
            </div>

            {/* Error Message Display */}
            {errorMessage && (
              <div className="p-3 bg-rose-950/40 border border-rose-500/50 rounded-xl flex items-center gap-2.5 text-xs text-rose-300">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                <span className="font-mono">{errorMessage}</span>
              </div>
            )}
          </div>
        </div>

        {/* Modal Action Footer */}
        <div className="px-5 py-3.5 border-t border-slate-800/80 bg-slate-950/60 flex items-center gap-3">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleDecision('REJECTED')}
            className="flex-1 px-4 py-2.5 rounded-xl text-xs font-semibold uppercase tracking-wider text-rose-200 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/40 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <XCircle className="w-4 h-4 text-rose-400" />
            <span>Reject Action</span>
          </button>

          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => handleDecision('APPROVED')}
            className="flex-1 px-4 py-2.5 rounded-xl text-xs font-semibold uppercase tracking-wider text-white bg-emerald-600 hover:bg-emerald-500 border border-emerald-500/40 shadow-lg shadow-emerald-950/50 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <CheckCircle className="w-4 h-4 text-emerald-100" />
            <span>Approve Execution</span>
          </button>
        </div>
      </div>
    </div>
  );
}

