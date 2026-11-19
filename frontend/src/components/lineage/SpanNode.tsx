'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Bot, Cpu, Wrench, ShieldAlert, Coins, Flame } from 'lucide-react';
import { cn } from '@/lib/cn';
import { LineageNodeDTO } from '@/types/telemetry';

export type SpanNodeType = Node<LineageNodeDTO, 'spanNode'>;

function formatDuration(ms?: number | null): string | null {
  if (ms === undefined || ms === null) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export const SpanNode = memo(function SpanNode({
  data,
  selected,
}: NodeProps<SpanNodeType>) {
  const {
    span_type,
    operation_name,
    attempt_number,
    agent_id,
    status,
    duration_ms,
    input_tokens,
    output_tokens,
    direct_cost_usd,
    rolled_up_cost_usd,
    cost_basis,
    is_root_cause,
  } = data;

  const totalTokens = (input_tokens || 0) + (output_tokens || 0);
  const formattedDuration = formatDuration(duration_ms);

  // Status highlights and styles
  const isRunning = status === 'RUNNING';
  const isAwaiting = status === 'AWAITING_APPROVAL';
  const isStalled = status === 'STALLED';
  const isSucceeded = status === 'SUCCEEDED';
  const isFailed = status === 'FAILED' || status === 'TIMED_OUT';

  const borderClass = isRunning
    ? 'border-sky-500 shadow-sky-500/20 ring-1 ring-sky-500/30 animate-pulse'
    : isAwaiting
    ? 'border-amber-500 shadow-amber-500/20 ring-1 ring-amber-500/30 animate-pulse'
    : isStalled
    ? 'border-purple-500 shadow-purple-500/30 ring-1 ring-purple-500/40'
    : isFailed
    ? 'border-rose-500 shadow-rose-500/30 ring-1 ring-rose-500/30'
    : isSucceeded
    ? 'border-emerald-500/40 hover:border-emerald-500/80'
    : 'border-slate-800 hover:border-slate-700';

  const statusPillClass = isRunning
    ? 'bg-sky-500/20 text-sky-300 border-sky-500/40'
    : isAwaiting
    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
    : isStalled
    ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
    : isFailed
    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
    : isSucceeded
    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
    : 'bg-slate-800 text-slate-400 border-slate-700';

  // Icon by span_type
  let IconComponent = Bot;
  let iconColor = 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30';
  if (span_type === 'LLM') {
    IconComponent = Cpu;
    iconColor = 'text-purple-400 bg-purple-500/10 border-purple-500/30';
  } else if (span_type === 'TOOL') {
    IconComponent = Wrench;
    iconColor = 'text-amber-400 bg-amber-500/10 border-amber-500/30';
  } else if (span_type === 'APPROVAL') {
    IconComponent = ShieldAlert;
    iconColor = 'text-rose-400 bg-rose-500/10 border-rose-500/30';
  }

  return (
    <div
      className={cn(
        'w-64 rounded-lg border bg-slate-900/95 p-3 shadow-lg transition-all cursor-pointer backdrop-blur-sm relative',
        borderClass,
        selected && 'ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-950',
        is_root_cause && 'ring-2 ring-rose-500 shadow-rose-950/60 ring-offset-1 ring-offset-slate-950'
      )}
    >
      {/* Prominent Top-Right Root Cause Badge */}
      {is_root_cause && (
        <div className="absolute -top-3 -right-2.5 flex items-center gap-1 bg-rose-600 text-white font-bold tracking-wider text-[10px] px-2 py-0.5 rounded-full shadow-lg shadow-rose-950/80 border border-rose-400 z-10">
          <Flame className="w-3 h-3 fill-white text-white" />
          <span>ROOT CAUSE</span>
        </div>
      )}

      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-slate-400 !border-2 !border-slate-900 transition-colors"
      />

      {/* Header Row: Icon, Operation Name, Attempt Pill */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={cn(
              'p-1.5 rounded-md border flex items-center justify-center shrink-0',
              iconColor
            )}
          >
            <IconComponent className="w-3.5 h-3.5" />
          </div>
          <span
            className="text-xs font-semibold text-slate-100 truncate tracking-tight"
            title={operation_name}
          >
            {operation_name}
          </span>
        </div>

        {attempt_number && attempt_number > 1 && (
          <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-mono font-medium rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
            #{attempt_number}
          </span>
        )}
      </div>

      {/* Subheader: Agent ID */}
      <div className="mt-1.5 flex items-center justify-between text-[11px] font-mono text-slate-400 truncate">
        <span className="truncate" title={agent_id}>
          {agent_id}
        </span>
        {is_root_cause && (
          <span className="shrink-0 text-[10px] uppercase font-bold text-rose-400 px-1 rounded bg-rose-950/60 border border-rose-800/60">
            ROOT CAUSE
          </span>
        )}
      </div>

      {/* Cost Metric Row */}
      {(span_type === 'LLM' || span_type === 'AGENT' || cost_basis === 'UNKNOWN') && (
        <div className="mt-2 flex items-center justify-between text-[11px] font-mono">
          <span className="text-slate-400 text-[10px] flex items-center gap-1">
            <Coins className="w-3 h-3 text-slate-400" />
            {span_type === 'AGENT' ? 'Subtree Spend:' : span_type === 'LLM' ? 'Direct Cost:' : 'Attribution:'}
          </span>
          {span_type === 'LLM' ? (
            cost_basis === 'UNKNOWN' || direct_cost_usd === null || direct_cost_usd === undefined ? (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-amber-500/15 text-amber-300 border-amber-500/40"
                title="Missing token usage or pricing model metadata"
              >
                Cost: Unknown
              </span>
            ) : (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                title={`Direct cost: $${Number(direct_cost_usd).toFixed(6)}`}
              >
                ${Number(direct_cost_usd).toFixed(4)}
              </span>
            )
          ) : span_type === 'AGENT' ? (
            rolled_up_cost_usd !== null && rolled_up_cost_usd !== undefined ? (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-indigo-500/15 text-indigo-300 border-indigo-500/30"
                title={`Subtree spend: $${Number(rolled_up_cost_usd).toFixed(6)}`}
              >
                Σ ${Number(rolled_up_cost_usd).toFixed(4)}
              </span>
            ) : (
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-amber-500/15 text-amber-300 border-amber-500/40"
                title="Subtree costs unknown"
              >
                Cost: Unknown
              </span>
            )
          ) : cost_basis === 'UNKNOWN' ? (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border bg-amber-500/15 text-amber-300 border-amber-500/40">
              Cost: Unknown
            </span>
          ) : null}
        </div>
      )}

      {/* Footer Row: Status Pill, Duration, Token Count Badge */}
      <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1 text-[11px]">
        <span
          className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border uppercase tracking-wider',
            statusPillClass
          )}
        >
          {status}
        </span>

        <div className="flex items-center gap-2 shrink-0 font-mono text-slate-400 text-[11px]">
          {formattedDuration && (
            <span>{formattedDuration}</span>
          )}
          {totalTokens > 0 && (
            <span
              className="flex items-center gap-1 text-slate-300"
              title={`Tokens: ${input_tokens || 0} in / ${output_tokens || 0} out`}
            >
              <Coins className="w-3 h-3 text-slate-400" />
              {totalTokens.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-slate-400 !border-2 !border-slate-900 transition-colors"
      />
    </div>
  );
});

