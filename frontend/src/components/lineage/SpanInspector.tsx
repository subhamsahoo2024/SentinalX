'use client';

import { useState } from 'react';
import {
  X,
  Copy,
  Check,
  AlertTriangle,
  Bot,
  Cpu,
  Wrench,
  ShieldAlert,
  Clock,
  Coins,
  DollarSign,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { LineageNodeDTO } from '@/types/telemetry';

interface SpanInspectorProps {
  span: LineageNodeDTO | null;
  traceId?: string | null;
  onClose: () => void;
}

export function SpanInspector({ span, traceId, onClose }: SpanInspectorProps) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!span) return null;

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const totalTokens = (span.input_tokens || 0) + (span.output_tokens || 0);

  let IconComponent = Bot;
  if (span.span_type === 'LLM') IconComponent = Cpu;
  else if (span.span_type === 'TOOL') IconComponent = Wrench;
  else if (span.span_type === 'APPROVAL') IconComponent = ShieldAlert;

  const isFailed = span.status === 'FAILED' || span.status === 'TIMED_OUT';

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[500px] bg-slate-900/98 border-l border-slate-800 shadow-2xl flex flex-col backdrop-blur-md animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-300 shrink-0">
            <IconComponent className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-100 truncate">
                {span.operation_name}
              </h3>
              {span.attempt_number && span.attempt_number > 1 && (
                <span className="px-1.5 py-0.2 text-[10px] font-mono font-medium rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Attempt #{span.attempt_number}
                </span>
              )}
            </div>
            <p className="text-[11px] font-mono text-slate-400 mt-0.5">
              {span.span_type} · {span.agent_id}
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          title="Close Inspector"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 text-sm">
        {/* Error Banner */}
        {(isFailed || span.error_class || span.error_message) && (
          <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-300">
            <div className="flex items-center gap-2 font-semibold text-xs tracking-wide uppercase text-rose-200">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{span.error_class || 'Span Execution Error'}</span>
            </div>
            {span.error_message && (
              <p className="mt-1.5 text-xs text-rose-300 font-mono break-words leading-relaxed">
                {span.error_message}
              </p>
            )}
          </div>
        )}

        {/* Root Cause Banner */}
        {span.is_root_cause && (
          <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-600/60 text-rose-200 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
            Deterministic Anomaly Root Cause Identified
          </div>
        )}

        {/* Identity & References */}
        <div className="space-y-2.5">
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Identifiers
          </h4>
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 space-y-2 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Span ID</span>
              <button
                onClick={() => copyToClipboard(span.span_id, 'span_id')}
                className="flex items-center gap-1.5 text-slate-200 hover:text-cyan-400 transition-colors"
              >
                <span>{span.span_id}</span>
                {copiedKey === 'span_id' ? (
                  <Check className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Copy className="w-3 h-3 text-slate-500" />
                )}
              </button>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-500">Parent Span</span>
              <span className="text-slate-300">
                {span.parent_span_id || 'root (null)'}
              </span>
            </div>

            {traceId && (
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Trace ID</span>
                <button
                  onClick={() => copyToClipboard(traceId, 'trace_id')}
                  className="flex items-center gap-1.5 text-slate-200 hover:text-cyan-400 transition-colors"
                >
                  <span className="truncate max-w-[180px]">{traceId}</span>
                  {copiedKey === 'trace_id' ? (
                    <Check className="w-3 h-3 text-emerald-400" />
                  ) : (
                    <Copy className="w-3 h-3 text-slate-500" />
                  )}
                </button>
              </div>
            )}

            <div className="flex items-center justify-between pt-1 border-t border-slate-900">
              <span className="text-slate-500">Status</span>
              <span
                className={cn(
                  'px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider',
                  span.status === 'SUCCEEDED' && 'bg-emerald-500/20 text-emerald-300',
                  span.status === 'RUNNING' && 'bg-sky-500/20 text-sky-300',
                  span.status === 'AWAITING_APPROVAL' && 'bg-amber-500/20 text-amber-300',
                  (span.status === 'FAILED' || span.status === 'TIMED_OUT') &&
                    'bg-rose-500/20 text-rose-300'
                )}
              >
                {span.status}
              </span>
            </div>
          </div>
        </div>

        {/* Execution Timing */}
        <div className="space-y-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Execution Timing</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800/80">
              <span className="text-slate-500 block text-[10px] uppercase">Duration</span>
              <span className="text-slate-200 font-semibold text-sm mt-0.5 block">
                {span.duration_ms !== null && span.duration_ms !== undefined
                  ? span.duration_ms < 1000
                    ? `${Math.round(span.duration_ms)}ms`
                    : `${(span.duration_ms / 1000).toFixed(2)}s`
                  : 'In progress'}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800/80">
              <span className="text-slate-500 block text-[10px] uppercase">Started At</span>
              <span className="text-slate-300 text-xs mt-0.5 block truncate">
                {span.started_at ? new Date(span.started_at).toLocaleTimeString() : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Model, Tokens & Cost */}
        <div className="space-y-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider">
            <Coins className="w-3.5 h-3.5 text-slate-400" />
            <span>Model & Resource Metrics</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 space-y-2 text-xs">
            {(span.model_provider || span.model_name) && (
              <div className="flex items-center justify-between font-mono">
                <span className="text-slate-500">Model</span>
                <span className="text-slate-200 font-medium">
                  {span.model_provider ? `${span.model_provider}/` : ''}
                  {span.model_name || 'custom'}
                </span>
              </div>
            )}

            <div className="flex items-center justify-between font-mono">
              <span className="text-slate-500">Input Tokens</span>
              <span className="text-slate-300">
                {(span.input_tokens || 0).toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between font-mono">
              <span className="text-slate-500">Output Tokens</span>
              <span className="text-slate-300">
                {(span.output_tokens || 0).toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between font-mono pt-1.5 border-t border-slate-900">
              <span className="text-slate-400 font-medium">Total Tokens</span>
              <span className="text-slate-100 font-bold">
                {totalTokens.toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between font-mono pt-1.5 border-t border-slate-900">
              <span className="text-slate-500 flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-slate-500" />
                Cost Attribution
              </span>
              <span className="text-slate-200">
                {span.direct_cost_usd !== null && span.direct_cost_usd !== undefined
                  ? `$${span.direct_cost_usd.toFixed(6)}`
                  : 'Unknown'}
                <span className="text-slate-500 text-[10px] ml-1">
                  ({span.cost_basis || 'UNKNOWN'})
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Attributes (Inputs / Outputs / Metadata) */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Attributes & Payloads
            </h4>
            {span.attributes && Object.keys(span.attributes).length > 0 && (
              <button
                onClick={() =>
                  copyToClipboard(
                    JSON.stringify(span.attributes, null, 2),
                    'attributes'
                  )
                }
                className="text-xs font-mono text-slate-400 hover:text-cyan-400 flex items-center gap-1 transition-colors"
              >
                {copiedKey === 'attributes' ? (
                  <Check className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
                Copy JSON
              </button>
            )}
          </div>

          {span.attributes && Object.keys(span.attributes).length > 0 ? (
            <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300 overflow-x-auto max-h-96 leading-relaxed selection:bg-cyan-900">
              {JSON.stringify(span.attributes, null, 2)}
            </pre>
          ) : (
            <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800/60 text-slate-500 text-xs font-mono text-center">
              No payload attributes recorded for this span.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

