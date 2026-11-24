'use client';

import { useMemo, useSyncExternalStore } from 'react';
import {
  Bot,
  Cpu,
  Wrench,
  ShieldAlert,
  Clock,
  Flame,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { LineageNodeDTO } from '@/types/telemetry';

let cachedNow = typeof window !== 'undefined' ? Date.now() : 0;
const listeners = new Set<() => void>();

if (typeof window !== 'undefined') {
  setInterval(() => {
    cachedNow = Date.now();
    listeners.forEach((listener) => listener());
  }, 1000);
}

function subscribeTime(callback: () => void) {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

function getSnapshotTime(): number {
  return cachedNow;
}

function getServerSnapshotTime(): number {
  return 0;
}

export interface WaterfallViewProps {
  nodes: LineageNodeDTO[];
  selectedSpanId?: string | null;
  impactedSpanIds?: string[];
  onSelectSpan: (node: LineageNodeDTO) => void;
}

function formatDuration(ms: number): string {
  if (isNaN(ms) || ms < 0) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 10000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function getSpanTypeIcon(spanType: string) {
  const typeUpper = spanType.toUpperCase();
  if (typeUpper === 'LLM') {
    return <Cpu className="w-3.5 h-3.5 text-cyan-400 shrink-0" />;
  }
  if (typeUpper === 'TOOL') {
    return <Wrench className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
  }
  if (typeUpper === 'APPROVAL') {
    return <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
  }
  return <Bot className="w-3.5 h-3.5 text-indigo-400 shrink-0" />;
}

function getBarColorClass(node: LineageNodeDTO): string {
  const statusUpper = (node.status || '').toUpperCase();
  const typeUpper = (node.span_type || '').toUpperCase();

  if (
    node.is_root_cause ||
    statusUpper === 'FAILED' ||
    statusUpper === 'TIMED_OUT' ||
    statusUpper === 'CANCELLED'
  ) {
    return 'bg-rose-500/85 border border-rose-400 shadow-sm shadow-rose-950/40';
  }

  if (statusUpper === 'AWAITING_APPROVAL') {
    return 'bg-amber-500/85 border border-amber-300 animate-pulse';
  }

  if (typeUpper === 'LLM') {
    return 'bg-cyan-500/80 border border-cyan-400';
  }

  if (typeUpper === 'TOOL') {
    return 'bg-emerald-500/80 border border-emerald-400';
  }

  if (typeUpper === 'AGENT') {
    return 'bg-indigo-500/80 border border-indigo-400';
  }

  return 'bg-slate-600/80 border border-slate-500';
}

export function WaterfallView({
  nodes,
  selectedSpanId,
  impactedSpanIds = [],
  onSelectSpan,
}: WaterfallViewProps) {
  const currentNow = useSyncExternalStore(
    subscribeTime,
    getSnapshotTime,
    getServerSnapshotTime
  );

  // Tree flattening & Depth-First Traversal
  const { flattened, traceStartMs, totalSpanMs } = useMemo(() => {
    if (!nodes || nodes.length === 0) {
      return { flattened: [], traceStartMs: 0, totalSpanMs: 1 };
    }

    const nodeSpanIds = new Set(nodes.map((n) => n.span_id || n.id));
    const childrenMap = new Map<string, LineageNodeDTO[]>();
    const roots: LineageNodeDTO[] = [];

    nodes.forEach((node) => {
      const parentId = node.parent_span_id;
      if (!parentId || !nodeSpanIds.has(parentId)) {
        roots.push(node);
      } else {
        const list = childrenMap.get(parentId) || [];
        list.push(node);
        childrenMap.set(parentId, list);
      }
    });

    const sortByStartedAt = (a: LineageNodeDTO, b: LineageNodeDTO) => {
      const aTime = Date.parse(a.started_at) || 0;
      const bTime = Date.parse(b.started_at) || 0;
      return aTime - bTime;
    };

    roots.sort(sortByStartedAt);
    childrenMap.forEach((children) => {
      children.sort(sortByStartedAt);
    });

    const items: { node: LineageNodeDTO; depth: number }[] = [];
    const visited = new Set<string>();

    const traverse = (node: LineageNodeDTO, depth: number) => {
      const spanKey = node.span_id || node.id;
      if (visited.has(spanKey)) return;
      visited.add(spanKey);

      items.push({ node, depth });

      const children = childrenMap.get(spanKey) || [];
      for (const child of children) {
        traverse(child, depth + 1);
      }
    };

    for (const root of roots) {
      traverse(root, 0);
    }

    // Safety fallback for any unvisited disconnected nodes
    for (const node of nodes) {
      const spanKey = node.span_id || node.id;
      if (!visited.has(spanKey)) {
        traverse(node, 0);
      }
    }

    // Timing math
    const referenceNow =
      currentNow > 0
        ? currentNow
        : Math.max(0, ...nodes.map((n) => Date.parse(n.started_at) || 0));

    const startTimes = nodes.map((n) => {
      const t = Date.parse(n.started_at);
      return isNaN(t) ? referenceNow : t;
    });

    const endTimes = nodes.map((n) => {
      if (n.ended_at) {
        const t = Date.parse(n.ended_at);
        return isNaN(t) ? referenceNow : t;
      }
      return referenceNow;
    });

    const startMs = Math.min(...startTimes);
    const endMs = Math.max(...endTimes);
    const spanMs = Math.max(1, endMs - startMs);

    return {
      flattened: items,
      traceStartMs: startMs,
      totalSpanMs: spanMs,
    };
  }, [nodes, currentNow]);

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full p-8 text-center bg-slate-950/60 rounded-xl border border-slate-800/80 font-mono text-xs text-slate-400">
        <Clock className="w-8 h-8 mb-2 text-slate-600" />
        <span className="font-semibold text-slate-300">No execution spans recorded</span>
        <span className="text-slate-500 mt-1">
          Spans will appear here in waterfall hierarchy as the run progresses.
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full bg-slate-950 rounded-xl border border-slate-800/80 overflow-hidden shadow-2xl">
      {/* Header Timeline Ruler */}
      <div className="sticky top-0 z-20 flex items-center bg-slate-900/95 backdrop-blur-md border-b border-slate-800 h-9 shrink-0 select-none">
        {/* Left: Execution Hierarchy Label */}
        <div className="w-80 shrink-0 px-4 flex items-center text-[11px] font-mono font-bold tracking-wider text-slate-400 uppercase border-r border-slate-800/80">
          Execution Hierarchy
        </div>

        {/* Right: Timeline Scale & Ticks */}
        <div className="flex-1 relative h-full flex items-center px-4 font-mono text-[10px] text-slate-400">
          <span className="absolute left-4">0ms</span>
          <span className="absolute left-[25%] -translate-x-1/2">
            25% ({formatDuration(totalSpanMs * 0.25)})
          </span>
          <span className="absolute left-[50%] -translate-x-1/2">
            50% ({formatDuration(totalSpanMs * 0.5)})
          </span>
          <span className="absolute left-[75%] -translate-x-1/2">
            75% ({formatDuration(totalSpanMs * 0.75)})
          </span>
          <span className="absolute right-4 text-right">
            100% ({formatDuration(totalSpanMs)})
          </span>
        </div>
      </div>

      {/* Waterfall Rows */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden divide-y divide-slate-800/40">
        {flattened.map(({ node, depth }) => {
          const spanKey = node.span_id || node.id;
          const isSelected =
            selectedSpanId === spanKey || selectedSpanId === node.id;
          const isImpacted =
            impactedSpanIds.includes(spanKey) || impactedSpanIds.includes(node.id);

          const nodeStart = Date.parse(node.started_at) || traceStartMs;
          const nodeEnd = node.ended_at
            ? Date.parse(node.ended_at)
            : (currentNow || nodeStart);
          const duration =
            node.duration_ms ?? Math.max(0, nodeEnd - nodeStart);

          const offsetPct = Math.max(
            0,
            Math.min(100, ((nodeStart - traceStartMs) / totalSpanMs) * 100)
          );
          const rawWidthPct = Math.max(1.2, (duration / totalSpanMs) * 100);
          const widthPct = Math.min(100 - offsetPct, rawWidthPct);

          const formattedDuration = formatDuration(duration);
          const barColorClass = getBarColorClass(node);

          return (
            <div
              key={spanKey}
              onClick={() => onSelectSpan(node)}
              className={cn(
                'group flex items-center h-9 cursor-pointer transition-colors select-none text-xs font-mono',
                isSelected
                  ? 'bg-slate-800/90 ring-1 ring-inset ring-cyan-500/40'
                  : isImpacted
                  ? 'bg-rose-950/20 hover:bg-rose-950/40'
                  : 'hover:bg-slate-900/60'
              )}
            >
              {/* Left Column: Indented Span Info */}
              <div
                className="w-80 shrink-0 h-full border-r border-slate-800/80 flex items-center gap-2 pr-3 overflow-hidden"
                style={{ paddingLeft: `${depth * 18 + 12}px` }}
              >
                {getSpanTypeIcon(node.span_type)}

                <span
                  className={cn(
                    'truncate font-medium transition-colors',
                    isSelected
                      ? 'text-cyan-300 font-semibold'
                      : 'text-slate-200 group-hover:text-white'
                  )}
                  title={`${node.operation_name} (${node.agent_id})`}
                >
                  {node.operation_name}
                </span>

                {(node.attempt_number ?? 1) > 1 && (
                  <span
                    className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 shrink-0"
                    title={`Attempt #${node.attempt_number}`}
                  >
                    #{node.attempt_number}
                  </span>
                )}

                {node.is_root_cause && (
                  <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider bg-rose-600 text-white shrink-0 border border-rose-400 shadow-sm shadow-rose-950">
                    <Flame className="w-2.5 h-2.5 fill-white text-white" />
                    <span>ROOT CAUSE</span>
                  </span>
                )}
              </div>

              {/* Right Column: Timeline Bar & Duration Label */}
              <div className="flex-1 relative h-9 flex items-center px-4 overflow-hidden">
                {/* Background Grid Guidelines */}
                <div className="absolute inset-y-0 left-[25%] w-px bg-slate-800/30 pointer-events-none" />
                <div className="absolute inset-y-0 left-[50%] w-px bg-slate-800/30 pointer-events-none" />
                <div className="absolute inset-y-0 left-[75%] w-px bg-slate-800/30 pointer-events-none" />

                {/* Horizontal Latency Bar */}
                <div
                  className={cn(
                    'absolute h-4 rounded-sm transition-all',
                    barColorClass,
                    isSelected && 'ring-2 ring-white/60'
                  )}
                  style={{
                    left: `${offsetPct}%`,
                    width: `${widthPct}%`,
                  }}
                  title={`${node.operation_name}: ${formattedDuration} (status: ${node.status})`}
                />

                {/* Monospace Duration Label */}
                <span
                  className={cn(
                    'absolute text-[10px] font-mono pointer-events-none whitespace-nowrap transition-colors',
                    offsetPct + widthPct > 88
                      ? 'text-right pr-2 text-slate-100 font-semibold drop-shadow-sm'
                      : 'text-slate-400 group-hover:text-slate-200'
                  )}
                  style={
                    offsetPct + widthPct > 88
                      ? {
                          right: `${Math.max(1, 100 - (offsetPct + widthPct))}%`,
                        }
                      : {
                          left: `${offsetPct + widthPct + 0.8}%`,
                        }
                  }
                >
                  {formattedDuration}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
