'use client';

import { useMemo } from 'react';
import { Bot, Cpu, ShieldAlert, Wrench } from 'lucide-react';
import { formatDurationMs } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { LineageNodeDTO } from '@/types/telemetry';

interface WaterfallViewProps {
  nodes: LineageNodeDTO[];
  selectedSpanId?: string | null;
  impactedSpanIds?: string[];
  onSelectSpan: (node: LineageNodeDTO) => void;
}

interface OrderedSpanRow {
  node: LineageNodeDTO;
  depth: number;
}

function SpanIcon({ type }: { type: string }) {
  const upper = type.toUpperCase();
  if (upper === 'LLM') {
    return <Cpu className="h-3.5 w-3.5 text-[#0257D5] dark:text-[#38BDF8] shrink-0" aria-hidden="true" />;
  }
  if (upper === 'TOOL') {
    return <Wrench className="h-3.5 w-3.5 text-[#008BB8] dark:text-[#00C2FF] shrink-0" aria-hidden="true" />;
  }
  if (upper === 'APPROVAL') {
    return <ShieldAlert className="h-3.5 w-3.5 text-amber-700 dark:text-amber-400 shrink-0" aria-hidden="true" />;
  }
  return <Bot className="h-3.5 w-3.5 text-[#041533] dark:text-slate-200 shrink-0" aria-hidden="true" />;
}

export function WaterfallView({
  nodes,
  selectedSpanId,
  impactedSpanIds = [],
  onSelectSpan,
}: WaterfallViewProps) {
  const { orderedRows, traceStartMs, totalDurationMs } = useMemo(() => {
    if (nodes.length === 0) {
      return { orderedRows: [] as OrderedSpanRow[], traceStartMs: 0, totalDurationMs: 1 };
    }

    const byParent = new Map<string | null, LineageNodeDTO[]>();
    const nodeIds = new Set(nodes.map((n) => n.span_id));

    let minStart = Infinity;
    let maxEnd = -Infinity;

    for (const n of nodes) {
      const s = Date.parse(n.started_at);
      const dur = n.duration_ms ?? 250;
      const e = n.ended_at ? Date.parse(n.ended_at) : s + dur;
      if (!Number.isNaN(s)) minStart = Math.min(minStart, s);
      if (!Number.isNaN(e)) maxEnd = Math.max(maxEnd, e);

      const parentKey =
        n.parent_span_id && nodeIds.has(n.parent_span_id) ? n.parent_span_id : null;
      const group = byParent.get(parentKey) || [];
      group.push(n);
      byParent.set(parentKey, group);
    }

    for (const list of byParent.values()) {
      list.sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at));
    }

    const rows: OrderedSpanRow[] = [];
    const visited = new Set<string>();

    const walk = (parentId: string | null, depth: number) => {
      const children = byParent.get(parentId) || [];
      for (const child of children) {
        if (visited.has(child.span_id)) continue;
        visited.add(child.span_id);
        rows.push({ node: child, depth });
        walk(child.span_id, depth + 1);
      }
    };

    walk(null, 0);

    for (const n of nodes) {
      if (!visited.has(n.span_id)) {
        rows.push({ node: n, depth: 0 });
      }
    }

    const safeMin = Number.isFinite(minStart) ? minStart : 0;
    const safeMax = Number.isFinite(maxEnd) ? maxEnd : safeMin + 1000;

    return {
      orderedRows: rows,
      traceStartMs: safeMin,
      totalDurationMs: Math.max(100, safeMax - safeMin),
    };
  }, [nodes]);

  const impactedSet = useMemo(() => new Set(impactedSpanIds), [impactedSpanIds]);
  const rulerTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] overflow-hidden">
      <div className="grid grid-cols-12 border-b border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#0A1B3B] px-4 py-2.5 text-[11px] font-medium text-slate-600 dark:text-slate-300">
        <div className="col-span-5">Execution Hierarchy</div>
        <div className="col-span-7 flex items-center justify-between font-mono tabular-nums">
          {rulerTicks.map((ratio) => (
            <span key={ratio}>{formatDurationMs(totalDurationMs * ratio)}</span>
          ))}
        </div>
      </div>

      {orderedRows.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-500 dark:text-slate-400">
          No spans recorded for this execution trace.
        </div>
      ) : (
        <div className="divide-y divide-slate-100 dark:divide-[#15284B]">
          {orderedRows.map(({ node, depth }) => {
            const startMs = Date.parse(node.started_at);
            const durMs =
              node.duration_ms ??
              (node.ended_at ? Math.max(50, Date.parse(node.ended_at) - startMs) : 300);

            const offsetPct = Math.max(
              0,
              Math.min(98, ((startMs - traceStartMs) / totalDurationMs) * 100),
            );
            const widthPct = Math.max(
              1.5,
              Math.min(100 - offsetPct, (durMs / totalDurationMs) * 100),
            );

            const isSelected =
              selectedSpanId === node.span_id || selectedSpanId === node.id;
            const isFailed =
              node.status === 'FAILED' ||
              node.status === 'TIMED_OUT' ||
              impactedSet.has(node.span_id);

            let barColor = 'bg-[#0096D6]';
            if (isFailed) barColor = 'bg-red-600';
            else if (node.status === 'AWAITING_APPROVAL') barColor = 'bg-amber-500';
            else if (node.status === 'RUNNING') barColor = 'bg-[#00B4F0]';
            else if (node.status === 'STALLED') barColor = 'bg-violet-600';
            else if (node.span_type === 'LLM') barColor = 'bg-[#0257D5] dark:bg-[#38BDF8]';
            else if (node.span_type === 'AGENT') barColor = 'bg-[#041533] dark:bg-[#1D4ED8]';

            return (
              <button
                key={node.span_id}
                type="button"
                onClick={() => onSelectSpan(node)}
                className={cn(
                  'w-full grid grid-cols-12 items-center px-4 py-2.5 text-left hover:bg-[#F5F9FF] dark:hover:bg-[#0D2247] transition-colors',
                  isSelected && 'bg-[#EFF6FF] dark:bg-[#0257D5]/20',
                )}
              >
                <div
                  className="col-span-5 flex items-center gap-2 min-w-0 pr-3"
                  style={{ paddingLeft: `${Math.min(depth, 5) * 18}px` }}
                >
                  <SpanIcon type={node.span_type} />
                  <span className="text-xs font-medium text-slate-900 dark:text-slate-100 truncate">
                    {node.operation_name}
                  </span>
                  {(node.attempt_number ?? 1) > 1 && (
                    <span className="font-mono text-[10px] text-amber-800 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/60 rounded px-1 shrink-0">
                      #{node.attempt_number}
                    </span>
                  )}
                  {node.is_root_cause && (
                    <span className="rounded bg-red-100 dark:bg-red-950/70 px-1.5 py-0.5 text-[10px] font-semibold text-red-800 dark:text-red-300 shrink-0">
                      ROOT
                    </span>
                  )}
                </div>

                <div className="col-span-7 relative h-6 flex items-center">
                  <div className="w-full h-3 rounded-sm bg-slate-100 dark:bg-[#0E2247] relative overflow-hidden">
                    <div
                      className={cn('absolute top-0 bottom-0 rounded-sm', barColor)}
                      style={{ left: `${offsetPct}%`, width: `${widthPct}%` }}
                    />
                  </div>
                  <span
                    className="ml-2 font-mono text-[11px] tabular-nums text-slate-600 dark:text-slate-300 shrink-0"
                    style={{ minWidth: '58px', textAlign: 'right' }}
                  >
                    {formatDurationMs(durMs)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
