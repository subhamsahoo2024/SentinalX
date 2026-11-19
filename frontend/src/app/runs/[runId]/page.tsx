'use client';

import { Suspense, use, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Clock,
  Coins,
  DollarSign,
  Copy,
  Check,
  RefreshCw,
  Bot,
} from 'lucide-react';
import { fetchRunById, fetchRunLineage } from '@/lib/api';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import { LineageGraph } from '@/components/lineage/LineageGraph';
import { SpanInspector } from '@/components/lineage/SpanInspector';
import { LiveConnectionBadge } from '@/components/LiveConnectionBadge';
import { cn } from '@/lib/cn';
import {
  LineageGraphDTO,
  LineageNodeDTO,
  RunSummaryDTO,
} from '@/types/telemetry';

function RunDetailContent({
  params,
}: {
  params: Promise<{ runId?: string; run_id?: string }>;
}) {
  const resolvedParams = use(params);
  const runId = resolvedParams.runId || resolvedParams.run_id || '';

  const [run, setRun] = useState<RunSummaryDTO | null>(null);
  const [graph, setGraph] = useState<LineageGraphDTO | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<LineageNodeDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedRunId, setCopiedRunId] = useState(false);

  const refreshRunData = useCallback(async () => {
    if (!runId) return;
    try {
      const [runData, graphData] = await Promise.all([
        fetchRunById(runId),
        fetchRunLineage(runId),
      ]);
      setRun(runData);
      setGraph(graphData);
      setError(null);

      // Keep selected span fresh if already inspecting
      setSelectedSpan((prev) => {
        if (!prev) return null;
        return graphData.nodes.find((n) => n.id === prev.id) || prev;
      });
    } catch (err) {
      console.warn('Failed to load run telemetry:', err);
      setError(
        err instanceof Error ? err.message : 'Failed to load run telemetry'
      );
    }
  }, [runId]);

  // Initial fetch: microtask prevents synchronous setState within effect body
  useEffect(() => {
    let isMounted = true;
    if (!runId) return;

    Promise.all([fetchRunById(runId), fetchRunLineage(runId)])
      .then(([runData, graphData]) => {
        if (!isMounted) return;
        setRun(runData);
        setGraph(graphData);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        console.warn('Failed to load run telemetry:', err);
        setError(
          err instanceof Error ? err.message : 'Failed to load run telemetry'
        );
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [runId]);

  // Subscribe to live run WebSocket events
  const handleWsMessage = useCallback(
    (msg: { type?: string }) => {
      if (msg?.type === 'SPAN_UPSERT' || msg?.type === 'RUN_UPDATED') {
        refreshRunData();
      }
    },
    [refreshRunData]
  );

  const { status: wsStatus } = useWebSocketStream(
    `/ws/runs/${runId}`,
    handleWsMessage
  );

  const copyRunId = () => {
    navigator.clipboard.writeText(runId);
    setCopiedRunId(true);
    setTimeout(() => setCopiedRunId(false), 2000);
  };

  const status = run?.status || graph?.status;
  const isRunning = status === 'RUNNING';
  const isSucceeded = status === 'SUCCEEDED';
  const isFailed = status === 'FAILED' || status === 'TIMED_OUT';
  const isAwaiting = status === 'AWAITING_APPROVAL';

  const statusBadgeClass = isRunning
    ? 'bg-sky-500/20 text-sky-300 border-sky-500/40 animate-pulse'
    : isAwaiting
    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
    : isFailed
    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
    : isSucceeded
    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
    : 'bg-slate-800 text-slate-300 border-slate-700';

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] w-full overflow-hidden bg-slate-950">
      {/* Compact Top Navigation Bar */}
      <header className="h-14 px-4 sm:px-6 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md flex items-center justify-between gap-4 shrink-0 z-20">
        {/* Left: Back Link & Identity */}
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/"
            className="p-1.5 rounded-lg bg-slate-800 border border-slate-700/60 text-slate-400 hover:text-slate-100 hover:bg-slate-700 transition-colors"
            title="Back to Fleet Overview"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          <div className="flex items-center gap-2 min-w-0">
            <button
              onClick={copyRunId}
              className="flex items-center gap-1.5 text-sm font-bold text-slate-100 font-mono hover:text-cyan-400 transition-colors truncate"
              title="Click to copy run ID"
            >
              <span>Run: {runId}</span>
              {copiedRunId ? (
                <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-slate-500 shrink-0" />
              )}
            </button>

            {status && (
              <span
                className={cn(
                  'px-2 py-0.5 rounded text-[11px] font-mono font-semibold border uppercase tracking-wider shrink-0',
                  statusBadgeClass
                )}
              >
                {status}
              </span>
            )}
          </div>
        </div>

        {/* Right: Metrics & Live Badge */}
        <div className="flex items-center gap-2.5 sm:gap-3 text-xs font-mono text-slate-300 shrink-0">
          {run && (
            <>
              {/* Agent Badge */}
              <div
                className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-300"
                title={`Root Agent: ${run.agent_name || run.agent_id} (${run.team})`}
              >
                <Bot className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                <span className="truncate max-w-[120px]">
                  {run.agent_name || run.agent_id}
                </span>
              </div>

              {/* Duration Badge */}
              <div
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-300"
                title="Run Duration"
              >
                <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>
                  {run.duration_ms
                    ? run.duration_ms < 1000
                      ? `${Math.round(run.duration_ms)}ms`
                      : `${(run.duration_ms / 1000).toFixed(1)}s`
                    : 'running'}
                </span>
              </div>

              {/* Token Count Badge */}
              <div
                className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-300"
                title="Total Tokens Recorded"
              >
                <Coins className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span>{(run.total_tokens || 0).toLocaleString()}</span>
              </div>

              {/* Cost Badge */}
              <div
                className="hidden lg:flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700/60 text-slate-300"
                title="Attributed Direct Cost"
              >
                <DollarSign className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>
                  {run.total_cost_usd !== undefined && run.total_cost_usd !== null
                    ? Number(run.total_cost_usd).toFixed(4)
                    : '0.0000'}
                </span>
              </div>
            </>
          )}

          {/* Refresh Button */}
          <button
            onClick={refreshRunData}
            disabled={loading}
            className="p-1.5 rounded-lg bg-slate-800 border border-slate-700/60 text-slate-400 hover:text-slate-100 hover:bg-slate-700 transition-colors disabled:opacity-50"
            title="Refresh Lineage Graph"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>

          {/* Live WS Status Badge */}
          <LiveConnectionBadge status={wsStatus} />
        </div>
      </header>

      {/* Main Graph Viewport */}
      <main className="flex-1 w-full h-full relative overflow-hidden p-2 sm:p-3">
        {loading && !graph ? (
          <div className="flex flex-col items-center justify-center h-full w-full bg-slate-950/80 text-slate-400 font-mono text-sm">
            <RefreshCw className="w-8 h-8 mb-3 text-cyan-400 animate-spin" />
            <span>Loading agent lineage DAG...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full w-full p-6 text-center">
            <div className="max-w-md p-6 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-sm">
              <h4 className="font-bold text-rose-200 mb-1">Failed to load run</h4>
              <p className="font-mono text-xs">{error}</p>
              <button
                onClick={refreshRunData}
                className="mt-4 px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs transition-colors"
              >
                Retry
              </button>
            </div>
          </div>
        ) : graph ? (
          <LineageGraph
            graph={graph}
            selectedSpanId={selectedSpan?.id}
            onSelectSpan={setSelectedSpan}
          />
        ) : null}

        {/* Slide-over Span Inspector Drawer */}
        <SpanInspector
          span={selectedSpan}
          traceId={run?.trace_id || graph?.trace_id}
          onClose={() => setSelectedSpan(null)}
        />
      </main>
    </div>
  );
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ runId?: string; run_id?: string }>;
}) {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-[calc(100vh-3.5rem)] bg-slate-950 text-slate-400 font-mono text-sm">
          Loading run details...
        </div>
      }
    >
      <RunDetailContent params={params} />
    </Suspense>
  );
}
