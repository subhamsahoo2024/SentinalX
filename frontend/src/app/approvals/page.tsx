'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { format, formatDistanceToNow } from 'date-fns';
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  Layers,
  Lock,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  UserCheck,
  XCircle,
} from 'lucide-react';

import {
  fetchApprovals,
  fetchAuditEvents,
  submitApprovalDecision,
  verifyAuditChain,
} from '@/lib/api';
import { useApprovals } from '@/components/governance/ApprovalContext';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import {
  ActorRole,
  ApprovalDTO,
  AuditEventDTO,
  WebSocketMessage,
} from '@/types/telemetry';

type FilterTab = 'ALL' | 'PENDING' | 'APPROVED' | 'REJECTED';

function formatTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return format(d, 'yyyy-MM-dd HH:mm:ss');
  } catch {
    return dateStr;
  }
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

function RoleBadge({ role }: { role: string }) {
  const norm = role.toLowerCase();
  if (norm === 'admin') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/40">
        <Lock className="w-2.5 h-2.5" />
        ADMIN
      </span>
    );
  }
  if (norm === 'approver') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
        <UserCheck className="w-2.5 h-2.5" />
        APPROVER
      </span>
    );
  }
  if (norm === 'operator') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/40">
        OPERATOR
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700">
      {role.toUpperCase()}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const norm = status.toUpperCase();
  if (norm === 'PENDING') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-amber-500/10 text-amber-300 border border-amber-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        PENDING
      </span>
    );
  }
  if (norm === 'APPROVED') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
        <CheckCircle className="w-3 h-3 text-emerald-400" />
        APPROVED
      </span>
    );
  }
  if (norm === 'REJECTED') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-rose-500/10 text-rose-300 border border-rose-500/30">
        <XCircle className="w-3 h-3 text-rose-400" />
        REJECTED
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
      {norm}
    </span>
  );
}

function RiskBadge({ risk }: { risk: string }) {
  const norm = risk.toUpperCase();
  if (norm === 'CRITICAL') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-500/50">
        <AlertCircle className="w-2.5 h-2.5 text-rose-400" />
        CRITICAL RISK
      </span>
    );
  }
  if (norm === 'HIGH') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/50">
        <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
        HIGH RISK
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
      {norm}
    </span>
  );
}

interface ApprovalCardProps {
  approval: ApprovalDTO;
  onDecided: () => void;
}

function ApprovalCard({ approval, onDecided }: ApprovalCardProps) {
  const [selectedRole, setSelectedRole] = useState<ActorRole>('approver');
  const [comment, setComment] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showArgs, setShowArgs] = useState<boolean>(false);

  const isPending = approval.status === 'PENDING';

  const handleDecision = async (decision: 'APPROVED' | 'REJECTED') => {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await submitApprovalDecision(
        approval.approval_id,
        decision,
        comment,
        selectedRole
      );
      setComment('');
      onDecided();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className={`rounded-xl border transition-all ${
        isPending
          ? 'bg-slate-900/80 border-amber-500/40 shadow-lg shadow-amber-950/20'
          : 'bg-slate-900/40 border-slate-800/80'
      }`}
    >
      {/* Card Header */}
      <div className="p-4 sm:p-5 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <StatusBadge status={approval.status} />
          <RiskBadge risk={approval.risk_level} />
          <span className="font-mono text-cyan-400 font-semibold text-sm flex items-center gap-1 bg-cyan-950/40 border border-cyan-800/50 px-2 py-0.5 rounded">
            <Terminal className="w-3 h-3 text-cyan-400" />
            {approval.tool_name}()
          </span>
          <span className="text-xs font-mono text-slate-400">
            {approval.approval_id}
          </span>
        </div>

        <div className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-slate-400" />
          <span>{formatRelativeTime(approval.created_at)}</span>
        </div>
      </div>

      {/* Card Content */}
      <div className="p-4 sm:p-5 space-y-4">
        {/* Policy Reason */}
        <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-500/30 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs text-amber-200/90 leading-relaxed font-sans">
            <span className="font-semibold text-amber-300">Policy Reason: </span>
            {approval.policy_reason}
          </div>
        </div>

        {/* Identifiers Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center justify-between">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5 text-slate-400" />
              Agent:
            </span>
            <span className="text-slate-200 font-semibold truncate ml-2">
              {approval.agent_id}
            </span>
          </div>

          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center justify-between">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              Run:
            </span>
            <Link
              href={`/runs/${approval.run_id}`}
              className="text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 truncate ml-2"
            >
              <span className="truncate">{approval.run_id}</span>
              <ExternalLink className="w-3 h-3 shrink-0" />
            </Link>
          </div>

          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center justify-between">
            <span className="text-slate-400">Span ID:</span>
            <span className="text-slate-300 truncate ml-2">
              {approval.span_id}
            </span>
          </div>
        </div>

        {/* Sanitized Arguments Toggle */}
        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => setShowArgs(!showArgs)}
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-slate-200 transition-colors"
          >
            {showArgs ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            <span>Sanitized Tool Arguments</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
              {Object.keys(approval.sanitized_args || {}).length} params
            </span>
          </button>

          {showArgs && (
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3 overflow-x-auto text-xs font-mono text-cyan-300">
              <pre className="text-[11px] leading-relaxed">
                {JSON.stringify(approval.sanitized_args, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Resolved Details Banner */}
        {!isPending && (
          <div
            className={`p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono ${
              approval.status === 'APPROVED'
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                : 'bg-rose-950/20 border-rose-500/30 text-rose-200'
            }`}
          >
            <div className="flex items-center gap-2">
              {approval.status === 'APPROVED' ? (
                <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
              )}
              <span>
                Decided by{' '}
                <strong className="text-slate-100 font-semibold">
                  {approval.decided_by || 'Unknown'}
                </strong>{' '}
                on {formatTime(approval.decided_at)}
              </span>
            </div>
            {approval.comment && (
              <div className="text-slate-300 italic font-sans text-xs">
                &quot;{approval.comment}&quot;
              </div>
            )}
          </div>
        )}

        {/* Inline Decision Form (PENDING only) */}
        {isPending && (
          <div className="pt-2 border-t border-slate-800/80 space-y-3">
            {errorMessage && (
              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/50 flex items-start gap-2.5 text-xs text-rose-300">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <div className="font-semibold text-rose-200">
                    Authorization / Gate Error
                  </div>
                  <div className="font-mono text-[11px]">{errorMessage}</div>
                </div>
              </div>
            )}

            <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
              {/* Role Switcher */}
              <div className="flex items-center gap-2">
                <label className="text-xs font-mono text-slate-400 shrink-0 flex items-center gap-1">
                  <Lock className="w-3 h-3 text-slate-400" />
                  Actor Role:
                </label>
                <select
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value as ActorRole)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="approver">approver (Authorized)</option>
                  <option value="admin">admin (Authorized)</option>
                  <option value="operator">operator (403 Forbidden)</option>
                  <option value="viewer">viewer (403 Forbidden)</option>
                </select>
              </div>

              {/* Justification Comment */}
              <input
                type="text"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Audit justification comment..."
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-sans"
              />

              {/* Action Buttons */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => handleDecision('REJECTED')}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/40 hover:bg-rose-500/25 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-rose-950"
                >
                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                  <span>Reject</span>
                </button>
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => handleDecision('APPROVED')}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 hover:bg-emerald-500/30 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-emerald-950"
                >
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Approve</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ApprovalsPage() {
  const { refreshPending } = useApprovals();
  const [activeTab, setActiveTab] = useState<FilterTab>('ALL');
  const [approvals, setApprovals] = useState<ApprovalDTO[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventDTO[]>([]);
  const [chainVerification, setChainVerification] = useState<{
    valid: boolean;
    total_events: number;
    latest_hash: string;
    broken_at_audit_id: string | null;
  } | null>(null);
  const [isLoadingApprovals, setIsLoadingApprovals] = useState<boolean>(true);
  const [isLoadingAudit, setIsLoadingAudit] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [expandedPayloadId, setExpandedPayloadId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [apprList, auditList, verifyData] = await Promise.all([
        fetchApprovals(activeTab === 'ALL' ? undefined : activeTab),
        fetchAuditEvents(),
        verifyAuditChain().catch((err) => {
          console.warn('Failed to verify audit chain:', err);
          return null;
        }),
      ]);
      setApprovals(apprList);
      setAuditEvents(auditList);
      if (verifyData) setChainVerification(verifyData);
    } catch (err) {
      console.error('Failed to load governance data:', err);
    } finally {
      setIsLoadingApprovals(false);
      setIsLoadingAudit(false);
      setIsRefreshing(false);
    }
  }, [activeTab]);

  // Load initial data and on activeTab change
  useEffect(() => {
    let isMounted = true;
    Promise.all([
      fetchApprovals(activeTab === 'ALL' ? undefined : activeTab),
      fetchAuditEvents(),
      verifyAuditChain().catch((err) => {
        console.warn('Failed to verify audit chain:', err);
        return null;
      }),
    ])
      .then(([apprList, auditList, verifyData]) => {
        if (isMounted) {
          setApprovals(apprList);
          setAuditEvents(auditList);
          if (verifyData) setChainVerification(verifyData);
          setIsLoadingApprovals(false);
          setIsLoadingAudit(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error('Failed to load governance data:', err);
          setIsLoadingApprovals(false);
          setIsLoadingAudit(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [activeTab]);

  // Handle incoming live fleet WebSocket messages to keep page updated
  const handleWebSocketMessage = useCallback(
    (msg: WebSocketMessage<unknown>) => {
      if (!msg || typeof msg !== 'object') return;
      if (
        msg.type === 'APPROVAL_REQUIRED' ||
        msg.type === 'APPROVAL_DECIDED' ||
        msg.type === 'FLEET_UPDATED'
      ) {
        loadData();
        refreshPending();
      }
    },
    [loadData, refreshPending]
  );

  useWebSocketStream('/ws/fleet', handleWebSocketMessage);

  const onDecided = useCallback(() => {
    loadData();
    refreshPending();
  }, [loadData, refreshPending]);

  // Statistics
  const pendingCount = useMemo(
    () => approvals.filter((a) => a.status === 'PENDING').length,
    [approvals]
  );
  const approvedCount = useMemo(
    () => approvals.filter((a) => a.status === 'APPROVED').length,
    [approvals]
  );
  const rejectedCount = useMemo(
    () => approvals.filter((a) => a.status === 'REJECTED').length,
    [approvals]
  );

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Header & Overview */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-sm shadow-cyan-950">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
                Governance & Human-in-the-Loop Gate
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Runtime execution gates, role-based authorization (RBAC), and append-only audit trail
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={loadData}
          disabled={isRefreshing}
          className="self-start md:self-auto flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-mono font-medium bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-300 hover:text-slate-100 transition-colors shadow-sm disabled:opacity-50"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 text-cyan-400 ${
              isRefreshing ? 'animate-spin' : ''
            }`}
          />
          <span>{isRefreshing ? 'Refreshing...' : 'Refresh Console'}</span>
        </button>
      </div>

      {/* Metric Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Pending Gates</span>
            <Clock className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-amber-400 flex items-center gap-2">
            {pendingCount}
            {pendingCount > 0 && (
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            )}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Approved Actions</span>
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {approvedCount}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Rejected Actions</span>
            <XCircle className="w-3.5 h-3.5 text-rose-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-400">
            {rejectedCount}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Audit Log Entries</span>
            <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-purple-400">
            {auditEvents.length}
          </div>
        </div>
      </div>

      {/* Section 1: Runtime Approval Gates */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-400" />
            <h2 className="text-base font-semibold text-slate-100">
              Runtime Approval Gates
            </h2>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            {(['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as FilterTab[]).map(
              (tab) => {
                const active = activeTab === tab;
                return (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1 rounded-md transition-colors ${
                      active
                        ? 'bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/40 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab}
                  </button>
                );
              }
            )}
          </div>
        </div>

        {/* Approvals List */}
        {isLoadingApprovals ? (
          <div className="p-12 text-center text-slate-400 font-mono text-sm bg-slate-900/40 rounded-xl border border-slate-800">
            Loading approval requests...
          </div>
        ) : approvals.length === 0 ? (
          <div className="p-12 text-center rounded-xl bg-slate-900/30 border border-slate-800 space-y-2">
            <ShieldCheck className="w-10 h-10 text-slate-600 mx-auto" />
            <h3 className="text-sm font-semibold text-slate-300">
              No Approvals Found
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              There are currently no approval requests matching filter &quot;{activeTab}&quot;.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {approvals.map((approval) => (
              <ApprovalCard
                key={approval.approval_id}
                approval={approval}
                onDecided={onDecided}
              />
            ))}
          </div>
        )}
      </section>

      {/* Section 2: Immutable Governance Audit Log */}
      <section className="space-y-4 pt-4 border-t border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-purple-400" />
            <div>
              <h2 className="text-base font-semibold text-slate-100">
                Immutable Governance Audit Log
              </h2>
              <p className="text-xs text-slate-400">
                Append-only record of all authorization checks, approvals, and rejections
              </p>
            </div>
          </div>
        </div>

        {/* Cryptographic SHA-256 Hash Chain Integrity Banner */}
        {chainVerification && (
          <div
            className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono shadow-sm transition-all ${
              chainVerification.valid
                ? 'bg-emerald-950/25 border-emerald-500/40 text-emerald-200'
                : 'bg-rose-950/40 border-rose-500/60 text-rose-200 shadow-rose-950/40'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {chainVerification.valid ? (
                <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
              ) : (
                <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 animate-bounce" />
              )}
              <div>
                <div className="font-semibold text-slate-100 flex items-center gap-2">
                  {chainVerification.valid
                    ? `SHA-256 Audit Chain Verified (${chainVerification.total_events} records)`
                    : `Chain Integrity Breach at ${chainVerification.broken_at_audit_id}`}
                  {chainVerification.valid && (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      TAMPER-PROOF
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5 font-sans">
                  Cryptographic SHA-256 sequence linking guarantees append-only immutability and non-repudiation
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1.5 bg-slate-950/60 border border-slate-800/80 rounded-lg px-2.5 py-1 text-[11px] font-mono text-slate-300 self-start sm:self-auto shrink-0">
              <span className="text-slate-500">Latest Hash:</span>
              <code className="text-cyan-400 font-bold">
                {chainVerification.latest_hash
                  ? `${chainVerification.latest_hash.slice(0, 16)}...`
                  : 'GENESIS'}
              </code>
            </div>
          </div>
        )}

        {isLoadingAudit ? (
          <div className="p-8 text-center text-slate-400 font-mono text-sm bg-slate-900/40 rounded-xl border border-slate-800">
            Loading audit events...
          </div>
        ) : auditEvents.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-900/30 border border-slate-800 text-slate-500 text-xs font-mono">
            No audit events recorded yet.
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400 uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-3 px-4">Timestamp</th>
                    <th className="py-3 px-4">Action</th>
                    <th className="py-3 px-4">Actor ID</th>
                    <th className="py-3 px-4">Role</th>
                    <th className="py-3 px-4">Target ID</th>
                    <th className="py-3 px-4">Entry Hash</th>
                    <th className="py-3 px-4 text-right">Payload Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {auditEvents.map((evt) => {
                    const isExpanded = expandedPayloadId === evt.audit_id;
                    const isApproved = evt.action.includes('APPROVED');
                    const isRejected = evt.action.includes('REJECTED');

                    return (
                      <React.Fragment key={evt.audit_id}>
                        <tr className="hover:bg-slate-800/30 transition-colors">
                          <td className="py-3 px-4 whitespace-nowrap text-slate-300">
                            <div>{formatTime(evt.created_at)}</div>
                            <div className="text-[10px] text-slate-500">
                              {formatRelativeTime(evt.created_at)}
                            </div>
                          </td>

                          <td className="py-3 px-4 whitespace-nowrap">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                                isApproved
                                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                  : isRejected
                                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                  : 'bg-slate-800 text-slate-300 border border-slate-700'
                              }`}
                            >
                              {isApproved ? (
                                <CheckCircle className="w-2.5 h-2.5" />
                              ) : isRejected ? (
                                <XCircle className="w-2.5 h-2.5" />
                              ) : null}
                              {evt.action}
                            </span>
                          </td>

                          <td className="py-3 px-4 whitespace-nowrap text-slate-200 font-semibold">
                            {evt.actor_id}
                          </td>

                          <td className="py-3 px-4 whitespace-nowrap">
                            <RoleBadge role={evt.actor_role} />
                          </td>

                          <td className="py-3 px-4 whitespace-nowrap text-cyan-400">
                            {evt.target_type}:{evt.target_id}
                          </td>

                          <td className="py-3 px-4 whitespace-nowrap">
                            {evt.entry_hash ? (
                              <span
                                className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-cyan-300 font-mono text-[11px]"
                                title={evt.entry_hash}
                              >
                                {evt.entry_hash.slice(0, 10)}...
                              </span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>

                          <td className="py-3 px-4 text-right whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedPayloadId(
                                  isExpanded ? null : evt.audit_id
                                )
                              }
                              className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-cyan-300 transition-colors"
                            >
                              <span>{isExpanded ? 'Hide' : 'Inspect'}</span>
                              {isExpanded ? (
                                <ChevronDown className="w-3 h-3" />
                              ) : (
                                <ChevronRight className="w-3 h-3" />
                              )}
                            </button>
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr className="bg-slate-950/80">
                            <td colSpan={7} className="p-4 border-t border-slate-800/80">
                              <div className="space-y-2">
                                <div className="text-[11px] text-slate-400 font-sans flex items-center justify-between">
                                  <span>
                                    Audit ID: <code className="text-cyan-300">{evt.audit_id}</code>
                                  </span>
                                </div>
                                <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px] font-mono text-cyan-300 overflow-x-auto leading-relaxed">
                                  {JSON.stringify(evt.payload, null, 2)}
                                </pre>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
