'use client';

import { useState } from 'react';
import { AlertTriangle, Check, Copy, X } from 'lucide-react';
import { StatusBadge } from '@/components/StatusBadge';
import {
  formatDurationMs,
  formatTokens,
  formatUsd,
  formatUtcTimestamp,
} from '@/lib/format';
import type { LineageNodeDTO } from '@/types/telemetry';

interface SpanInspectorProps {
  span: LineageNodeDTO | null;
  traceId?: string | null;
  onClose: () => void;
}

function CopyableId({ label, value }: { label: string; value?: string | null }) {
  const [copied, setCopied] = useState(false);

  if (!value) {
    return (
      <div>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">{label}</p>
        <p className="mt-0.5 font-mono text-xs text-slate-400 dark:text-slate-500">—</p>
      </div>
    );
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div>
      <p className="text-[11px] text-slate-500 dark:text-slate-400">{label}</p>
      <button
        type="button"
        onClick={() => void copy()}
        className="mt-0.5 inline-flex items-center gap-1.5 font-mono text-xs text-slate-900 dark:text-slate-100 hover:text-[#0257D5] dark:hover:text-[#00C2FF] text-left break-all"
        title={`Copy ${label}`}
      >
        <span>{value}</span>
        {copied ? (
          <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400 shrink-0" aria-hidden="true" />
        ) : (
          <Copy className="h-3 w-3 text-slate-400 shrink-0" aria-hidden="true" />
        )}
      </button>
    </div>
  );
}

export function SpanInspector({ span, traceId, onClose }: SpanInspectorProps) {
  const [copiedJson, setCopiedJson] = useState(false);

  if (!span) return null;

  const totalTokens = (span.input_tokens ?? 0) + (span.output_tokens ?? 0);
  const rawPayload = JSON.stringify(span.attributes ?? {}, null, 2);

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(rawPayload);
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <aside
      aria-label="Span Inspector"
      className="fixed inset-y-0 right-0 z-30 w-full max-w-md border-l border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-xl flex flex-col"
    >
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
              {span.operation_name}
            </h2>
            {(span.attempt_number ?? 1) > 1 && (
              <span className="font-mono text-xs text-amber-800 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/60 rounded px-1.5 py-0.5">
                Attempt #{span.attempt_number}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 font-mono">
            {span.span_type} · {span.agent_id}
          </p>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
          aria-label="Close span inspector"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {span.is_root_cause && (
          <div className="rounded-md border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/50 p-3 text-xs text-red-900 dark:text-red-200 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-700 dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
            <div>
              <p className="font-semibold">Identified Root Cause Span</p>
              <p className="mt-0.5 text-red-800 dark:text-red-300">
                Failure propagation originated at this span and impacted downstream nodes.
              </p>
            </div>
          </div>
        )}

        {(span.error_class || span.error_message) && (
          <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50/70 dark:bg-red-950/40 p-3 text-xs">
            <p className="font-mono font-semibold text-red-900 dark:text-red-300">
              {span.error_class || 'ExecutionError'}
            </p>
            {span.error_message && (
              <p className="mt-1 text-red-800 dark:text-red-200 leading-relaxed">
                {span.error_message}
              </p>
            )}
          </div>
        )}

        <section className="space-y-3 border-b border-slate-200 dark:border-[#172E56] pb-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              Trace Identifiers
            </h3>
            <StatusBadge status={String(span.status)} compact />
          </div>
          <div className="grid grid-cols-1 gap-2.5">
            <CopyableId label="Span ID" value={span.span_id} />
            <CopyableId label="Parent Span ID" value={span.parent_span_id} />
            <CopyableId label="Trace ID" value={traceId} />
          </div>
        </section>

        <section className="grid grid-cols-2 gap-4 border-b border-slate-200 dark:border-[#172E56] pb-4 text-xs">
          <div>
            <p className="text-slate-500 dark:text-slate-400">Duration</p>
            <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {formatDurationMs(span.duration_ms)}
            </p>
          </div>
          <div>
            <p className="text-slate-500 dark:text-slate-400">Started At</p>
            <p className="mt-0.5 font-mono text-slate-900 dark:text-slate-100">
              {formatUtcTimestamp(span.started_at)}
            </p>
          </div>
        </section>

        <section className="space-y-3 border-b border-slate-200 dark:border-[#172E56] pb-4 text-xs">
          <h3 className="font-semibold text-slate-700 dark:text-slate-300">
            Model & Resource Attribution
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-slate-500 dark:text-slate-400">Model</p>
              <p className="mt-0.5 font-mono text-slate-900 dark:text-slate-100">
                {span.model_provider && span.model_name
                  ? `${span.model_provider}/${span.model_name}`
                  : '—'}
              </p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Cost Basis</p>
              <p className="mt-0.5 font-mono text-slate-900 dark:text-slate-100">
                {span.cost_basis || 'UNKNOWN'}
              </p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Tokens (In / Out / Total)</p>
              <p className="mt-0.5 font-mono tabular-nums text-slate-900 dark:text-slate-100">
                {formatTokens(span.input_tokens)} / {formatTokens(span.output_tokens)} /{' '}
                {formatTokens(totalTokens)}
              </p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Direct / Subtree Spend</p>
              <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {formatUsd(span.direct_cost_usd)} / {formatUsd(span.rolled_up_cost_usd)}
              </p>
            </div>
          </div>
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              Attributes & Payloads
            </h3>
            <button
              type="button"
              onClick={() => void handleCopyJson()}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-[#0257D5] dark:text-[#38BDF8] hover:underline"
            >
              {copiedJson ? (
                <>
                  <Check className="h-3 w-3" aria-hidden="true" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" aria-hidden="true" />
                  <span>Copy JSON</span>
                </>
              )}
            </button>
          </div>
          <pre className="max-h-60 overflow-auto rounded-md border border-slate-200 dark:border-[#172E56] bg-[#040B18] p-3 text-[11px] font-mono text-slate-100">
            {rawPayload}
          </pre>
        </section>
      </div>
    </aside>
  );
}
