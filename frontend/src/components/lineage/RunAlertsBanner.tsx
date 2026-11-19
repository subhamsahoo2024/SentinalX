'use client';

import { useState } from 'react';
import {
  AlertTriangle,
  Flame,
  Crosshair,
  CheckCircle2,
  Check,
  Loader2,
  ShieldAlert,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { AlertDTO } from '@/types/telemetry';

interface RunAlertsBannerProps {
  alerts: AlertDTO[];
  onFocusSpan?: (spanId: string) => void;
  onAcknowledgeAlert?: (alertId: string) => Promise<void> | void;
}

function getSeverityBadgeClass(severity: string): string {
  switch (severity?.toUpperCase()) {
    case 'CRITICAL':
      return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
    case 'HIGH':
      return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
    case 'MEDIUM':
      return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40';
    case 'LOW':
      return 'bg-blue-500/20 text-blue-300 border-blue-500/40';
    default:
      return 'bg-slate-700/40 text-slate-300 border-slate-600/40';
  }
}

function formatEvidencePills(
  evidence: Record<string, unknown>
): Array<{ label: string; value: string }> {
  if (!evidence || typeof evidence !== 'object') return [];

  const pills: Array<{ label: string; value: string }> = [];

  // Repeated Tool Loop (repeat_count / threshold)
  if (evidence.repeat_count !== undefined) {
    const val =
      evidence.threshold !== undefined
        ? `${evidence.repeat_count} / ${evidence.threshold}`
        : String(evidence.repeat_count);
    pills.push({ label: 'repeat_count', value: val });
  }

  // Token Budget Overrun (total_tokens / budget_limit)
  if (evidence.total_tokens !== undefined) {
    const total = Number(evidence.total_tokens).toLocaleString();
    const limit =
      evidence.budget_limit !== undefined
        ? Number(evidence.budget_limit).toLocaleString()
        : null;
    pills.push({
      label: 'total_tokens',
      value: limit ? `${total} / ${limit}` : total,
    });
  }

  // Cascading Failure (affected_count, origin_operation, error_class)
  if (evidence.affected_count !== undefined) {
    pills.push({
      label: 'affected_count',
      value: String(evidence.affected_count),
    });
  }
  if (evidence.tool_name && typeof evidence.tool_name === 'string') {
    pills.push({ label: 'tool_name', value: evidence.tool_name });
  }
  if (
    evidence.origin_operation &&
    typeof evidence.origin_operation === 'string'
  ) {
    pills.push({
      label: 'origin_operation',
      value: evidence.origin_operation,
    });
  }
  if (evidence.error_class && typeof evidence.error_class === 'string') {
    pills.push({ label: 'error_class', value: evidence.error_class });
  }
  if (evidence.window_seconds !== undefined) {
    pills.push({ label: 'window', value: `${evidence.window_seconds}s` });
  }
  if (evidence.stall_timeout_sec !== undefined) {
    pills.push({ label: 'timeout', value: `${evidence.stall_timeout_sec}s` });
  }

  return pills;
}

export function RunAlertsBanner({
  alerts,
  onFocusSpan,
  onAcknowledgeAlert,
}: RunAlertsBannerProps) {
  const [ackingIds, setAckingIds] = useState<Set<string>>(new Set());

  if (!alerts || alerts.length === 0) {
    return null;
  }

  const handleAck = async (alertId: string) => {
    if (!onAcknowledgeAlert || ackingIds.has(alertId)) return;
    setAckingIds((prev) => new Set(prev).add(alertId));
    try {
      await onAcknowledgeAlert(alertId);
    } finally {
      setAckingIds((prev) => {
        const next = new Set(prev);
        next.delete(alertId);
        return next;
      });
    }
  };

  return (
    <div className="mb-2 space-y-2 shrink-0">
      {alerts.map((alert) => {
        const isCritical = alert.severity?.toUpperCase() === 'CRITICAL';
        const evidencePills = formatEvidencePills(alert.evidence);
        const isAcking = ackingIds.has(alert.alert_id);

        return (
          <div
            key={alert.alert_id}
            className={cn(
              'p-3 rounded-lg border backdrop-blur-md transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg',
              isCritical
                ? 'bg-rose-950/40 border-rose-500/40 shadow-rose-950/30'
                : 'bg-slate-900/90 border-slate-800 shadow-slate-950/40',
              alert.acknowledged && 'opacity-70 bg-slate-900/60'
            )}
          >
            {/* Left Column: Severity, Rule Pill, Title & Evidence */}
            <div className="space-y-1.5 min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {/* Severity Badge */}
                <span
                  className={cn(
                    'px-2 py-0.5 rounded text-[11px] font-mono font-bold uppercase tracking-wider border flex items-center gap-1',
                    getSeverityBadgeClass(alert.severity)
                  )}
                >
                  {isCritical ? (
                    <Flame className="w-3 h-3 fill-rose-400" />
                  ) : (
                    <AlertTriangle className="w-3 h-3" />
                  )}
                  {alert.severity}
                </span>

                {/* Rule ID Pill */}
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700/80">
                  {alert.rule_id}
                </span>

                {/* Acknowledgement Status Indicator */}
                {alert.acknowledged && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                    <Check className="w-3 h-3" />
                    ACKNOWLEDGED
                  </span>
                )}
              </div>

              {/* Alert Title */}
              <h4 className="text-sm font-semibold text-slate-100 tracking-tight">
                {alert.title}
              </h4>

              {/* Formatted Key-Value Evidence Pills */}
              {evidencePills.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  {evidencePills.map((p, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-slate-950/80 text-slate-300 border border-slate-800"
                    >
                      <span className="text-slate-400 font-medium">
                        {p.label}:
                      </span>
                      <span className="text-cyan-300 font-semibold truncate max-w-[200px]">
                        {p.value}
                      </span>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Right Column: Action Buttons */}
            <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
              {/* Focus Origin Button */}
              {alert.origin_span_id && onFocusSpan && (
                <button
                  onClick={() => onFocusSpan(alert.origin_span_id!)}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-medium font-mono flex items-center gap-1.5 transition-colors shadow-sm"
                  title={`Focus origin span ${alert.origin_span_id}`}
                >
                  <Crosshair className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Focus Origin</span>
                </button>
              )}

              {/* Acknowledge Button */}
              {alert.acknowledged ? (
                <span className="px-2.5 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-400 text-xs font-mono flex items-center gap-1.5 cursor-default">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Acknowledged</span>
                </span>
              ) : (
                <button
                  onClick={() => handleAck(alert.alert_id)}
                  disabled={isAcking}
                  className="px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-200 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50 shadow-sm"
                >
                  {isAcking ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                  )}
                  <span>Acknowledge</span>
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
