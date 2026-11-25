'use client';

import { useState } from 'react';
import { CheckCircle2, Crosshair } from 'lucide-react';
import { StatusBadge } from '@/components/StatusBadge';
import { formatRelativeTime } from '@/lib/format';
import type { AlertDTO } from '@/types/telemetry';

interface RunAlertsBannerProps {
  alerts: AlertDTO[];
  onFocusSpan?: (spanId: string) => void;
  onAcknowledgeAlert?: (alertId: string) => Promise<void> | void;
}

export function RunAlertsBanner({
  alerts,
  onFocusSpan,
  onAcknowledgeAlert,
}: RunAlertsBannerProps) {
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  if (alerts.length === 0) return null;

  const handleAck = async (alertId: string) => {
    if (!onAcknowledgeAlert) return;
    setAcknowledgingId(alertId);
    try {
      await onAcknowledgeAlert(alertId);
    } finally {
      setAcknowledgingId(null);
    }
  };

  return (
    <div className="space-y-2.5">
      {alerts.map((alert) => (
        <div
          key={alert.alert_id}
          className="rounded-lg border border-red-200 dark:border-red-800/80 bg-red-50/60 dark:bg-red-950/35 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        >
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <StatusBadge status={alert.severity} compact />
              <span className="font-mono text-xs font-semibold text-red-900 dark:text-red-300">
                {alert.rule_id}
              </span>
              <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {alert.title}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {formatRelativeTime(alert.created_at)}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700 dark:text-slate-300">
              {Object.entries(alert.evidence || {}).map(([k, v]) => (
                <span key={k} className="font-mono">
                  <span className="text-slate-500 dark:text-slate-400">{k}:</span>{' '}
                  <strong className="font-semibold text-slate-900 dark:text-slate-100">
                    {typeof v === 'string' ? v : JSON.stringify(v)}
                  </strong>
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {alert.origin_span_id && onFocusSpan && (
              <button
                type="button"
                onClick={() => onFocusSpan(alert.origin_span_id!)}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650] transition-colors whitespace-nowrap"
              >
                <Crosshair className="h-3.5 w-3.5 text-red-700 dark:text-red-400" aria-hidden="true" />
                <span>Focus Origin</span>
              </button>
            )}
            {!alert.acknowledged && onAcknowledgeAlert && (
              <button
                type="button"
                disabled={acknowledgingId === alert.alert_id}
                onClick={() => void handleAck(alert.alert_id)}
                className="inline-flex items-center gap-1.5 rounded-md bg-[#041533] dark:bg-[#0257D5] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#0257D5] dark:hover:bg-[#0346B0] disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>
                  {acknowledgingId === alert.alert_id ? 'Acknowledging...' : 'Acknowledge'}
                </span>
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
