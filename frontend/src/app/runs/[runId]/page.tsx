'use client';

import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import {
  ArrowLeft,
  Check,
  Copy,
  GitBranch,
  History,
  ListTree,
  OctagonAlert,
  RefreshCw,
} from 'lucide-react';
import { LiveConnectionBadge } from '@/components/LiveConnectionBadge';
import { StatusBadge } from '@/components/StatusBadge';
import { LineageGraph } from '@/components/lineage/LineageGraph';
import { RunAlertsBanner } from '@/components/lineage/RunAlertsBanner';
import { SpanInspector } from '@/components/lineage/SpanInspector';
import { WaterfallView } from '@/components/lineage/WaterfallView';
import { TimelineReplay } from '@/components/replay/TimelineReplay';
import { useIsClient } from '@/hooks/use-is-client';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import {
  acknowledgeAlert,
  cancelRun,
  fetchAlerts,
  fetchRunById,
  fetchRunLineage,
} from '@/lib/api';
import { getStoredUser } from '@/lib/auth';
import {
  computeRunDurationMs,
  formatDurationMs,
  formatTokens,
  formatUsd,
} from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  AlertDTO,
  LineageEdgeDTO,
  LineageGraphDTO,
  LineageNodeDTO,
  RunSummaryDTO,
  WebSocketMessage,
} from '@/types/telemetry';

type ViewMode = 'dag' | 'waterfall';

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ runId?: string; run_id?: string }>;
}) {
  const resolvedParams = use(params);
  const rawRunId = resolvedParams.runId || resolvedParams.run_id || '';
  const decodedRunId = decodeURIComponent(rawRunId);

  const [run, setRun] = useState<RunSummaryDTO | null>(null);
  const [graph, setGraph] = useState<LineageGraphDTO | null>(null);
  const [alerts, setAlerts] = useState<AlertDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('dag');
  const [selectedSpan, setSelectedSpan] = useState<LineageNodeDTO | null>(null);
  const [replayMode, setReplayMode] = useState(false);
  const [replayGraph, setReplayGraph] = useState<LineageGraphDTO | null>(null);
  const [copiedId, setCopiedId] = useState(false);
  const [killModalOpen, setKillModalOpen] = useState(false);
  const [killing, setKilling] = useState(false);
  const [killError, setKillError] = useState<string | null>(null);
  const [liveNow, setLiveNow] = useState<number>(() => Date.now());
  const mounted = useIsClient();
  const inspectorSuppressedRef = useRef(false);
  const graphRef = useRef<LineageGraphDTO | null>(null);

  useEffect(() => {
    graphRef.current = graph;
  }, [graph]);

  const loadRunData = useCallback(async () => {
    if (!decodedRunId) return null;
    const [runDetail, lineageData, alertsData] = await Promise.all([
      fetchRunById(decodedRunId),
      fetchRunLineage(decodedRunId),
      fetchAlerts({ run_id: decodedRunId }),
    ]);
    setRun(runDetail);
    setGraph(lineageData);
    setAlerts(alertsData);
    setError(null);
    setSelectedSpan((prev) => {
      if (!prev) return null;
      return lineageData.nodes.find((n) => n.id === prev.id) || prev;
    });
    return { runDetail, lineageData };
  }, [decodedRunId]);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    if (!decodedRunId) return;

    const initialLoadWithRetry = async () => {
      setLoading(true);
      while (!cancelled && attempts < 10) {
        try {
          const res = await loadRunData();
          if (res?.runDetail || res?.lineageData) {
            break;
          }
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          if (
            (msg.includes('404') || msg.toLowerCase().includes('not found')) &&
            attempts < 9
          ) {
            attempts += 1;
            await new Promise((r) => setTimeout(r, 500));
            continue;
          }
          if (!cancelled) {
            setError(msg);
          }
          break;
        }
        attempts += 1;
        await new Promise((r) => setTimeout(r, 500));
      }
      if (!cancelled) setLoading(false);
    };

    void initialLoadWithRetry();
    return () => {
      cancelled = true;
    };
  }, [decodedRunId, loadRunData]);

  const handleWsMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (
        msg.type === 'SPAN_UPSERT' ||
        msg.type === 'RUN_UPDATED' ||
        msg.type === 'ALERT_CREATED'
      ) {
        void loadRunData().catch((err) => console.warn('Refresh failed:', err));
      }
    },
    [loadRunData],
  );

  const { status: wsStatus } = useWebSocketStream<WebSocketMessage>(
    `/ws/runs/${encodeURIComponent(decodedRunId)}`,
    handleWsMessage,
  );

  const status = run?.status || graph?.status;
  const isRunInFlight = status === 'RUNNING' || status === 'AWAITING_APPROVAL';

  useEffect(() => {
    if (status !== 'RUNNING') return;
    const poll = setInterval(() => {
      void loadRunData().catch((err) => console.warn('Polling refresh failed:', err));
    }, 4000);
    return () => clearInterval(poll);
  }, [status, loadRunData]);

  useEffect(() => {
    if (!isRunInFlight) return;
    const ticker = setInterval(() => {
      setLiveNow(Date.now());
    }, 1000);
    return () => clearInterval(ticker);
  }, [isRunInFlight]);

  const handleReplayFrame = useCallback(
    (
      nodes: LineageNodeDTO[],
      edges: LineageEdgeDTO[],
      activeNode: LineageNodeDTO | null,
      isExplicitSelect?: boolean,
    ) => {
      const current = graphRef.current;
      if (current) {
        setReplayGraph({
          ...current,
          nodes,
          edges,
        });
      }
      if (activeNode) {
        if (isExplicitSelect) {
          inspectorSuppressedRef.current = false;
          setSelectedSpan(activeNode);
        } else if (!inspectorSuppressedRef.current) {
          setSelectedSpan(activeNode);
        }
      }
    },
    [],
  );

  const handleSelectSpan = useCallback((span: LineageNodeDTO | null) => {
    inspectorSuppressedRef.current = span === null;
    setSelectedSpan(span);
  }, []);

  const handleCloseInspector = useCallback(() => {
    inspectorSuppressedRef.current = true;
    setSelectedSpan(null);
  }, []);

  const activeGraph = replayMode && replayGraph ? replayGraph : graph;

  const impactedSpanIds = useMemo(() => {
    const ids = new Set<string>();
    for (const a of alerts) {
      for (const s of a.impacted_span_ids || []) ids.add(s);
    }
    return Array.from(ids);
  }, [alerts]);

  const durationMs = useMemo(() => {
    if (!run) return null;
    if (run.duration_ms !== undefined && run.duration_ms !== null) {
      return run.duration_ms;
    }
    if (run.ended_at) return computeRunDurationMs(run.started_at, run.ended_at);
    if (isRunInFlight) return Math.max(0, liveNow - Date.parse(run.started_at));
    return null;
  }, [run, isRunInFlight, liveNow]);

  const handleCopyRunId = async () => {
    try {
      await navigator.clipboard.writeText(decodedRunId);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 1500);
    } catch {
      // ignore
    }
  };

  const handleFocusSpan = (spanId: string) => {
    const found = graph?.nodes.find((n) => n.span_id === spanId || n.id === spanId);
    if (found) {
      inspectorSuppressedRef.current = false;
      setSelectedSpan(found);
    }
  };

  const handleAckAlert = async (alertId: string) => {
    try {
      const updated = await acknowledgeAlert(alertId);
      setAlerts((prev) =>
        prev.map((a) => (a.alert_id === alertId ? updated : a)),
      );
    } catch (err) {
      console.warn('Failed to acknowledge alert:', err);
    }
  };

  const handleKillRun = async () => {
    setKilling(true);
    setKillError(null);
    try {
      const actorRole = getStoredUser()?.role || 'approver';
      const updated = await cancelRun(decodedRunId, actorRole);
      setRun(updated);
      setKillModalOpen(false);
      await loadRunData();
    } catch (err: unknown) {
      setKillError(err instanceof Error ? err.message : 'Failed to abort run');
    } finally {
      setKilling(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-wrap">
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] px-2.5 py-1.5 text-xs font-medium text-[#061838] dark:text-slate-200 hover:bg-[#EFF6FF] dark:hover:bg-[#0D2247]"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Fleet</span>
            </Link>

            <button
              type="button"
              onClick={() => void handleCopyRunId()}
              className="inline-flex items-center gap-1.5 font-mono text-sm font-semibold text-[#041533] dark:text-slate-100 hover:text-[#0257D5] dark:hover:text-[#00C2FF]"
              title="Copy Run ID"
            >
              <span>{decodedRunId}</span>
              {copiedId ? (
                <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
              )}
            </button>

            {status && <StatusBadge status={String(status)} />}
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <div className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-[#0A1B3B] border border-transparent dark:border-[#172E56] p-1">
              <button
                type="button"
                onClick={() => setViewMode('dag')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  viewMode === 'dag'
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0257D5] dark:text-white'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
                )}
              >
                <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Lineage DAG</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('waterfall')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  viewMode === 'waterfall'
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0257D5] dark:text-white'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
                )}
              >
                <ListTree className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Latency Waterfall</span>
              </button>
            </div>

            {isRunInFlight && (
              <button
                type="button"
                onClick={() => {
                  setKillError(null);
                  setKillModalOpen(true);
                }}
                className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
              >
                <OctagonAlert className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Kill Run</span>
              </button>
            )}

            <LiveConnectionBadge status={wsStatus} />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 dark:border-[#172E56] pt-3 text-xs text-slate-600 dark:text-slate-400">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
            <span>
              Root Agent:{' '}
              <strong className="font-mono text-slate-900 dark:text-slate-100">
                {run?.agent_name || run?.agent_id || '—'}
              </strong>
            </span>
            <span>
              Team:{' '}
              <strong className="font-mono text-slate-900 dark:text-slate-100">
                {run?.team || '—'}
              </strong>
            </span>
            <span>
              Duration:{' '}
              <strong className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                {formatDurationMs(durationMs)}
              </strong>
            </span>
            <span>
              Tokens:{' '}
              <strong className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                {formatTokens(run?.total_tokens)}
              </strong>
            </span>
            <span>
              Attributed Cost:{' '}
              <strong className="font-mono tabular-nums text-slate-900 dark:text-slate-100">
                {formatUsd(run?.total_cost_usd)}
              </strong>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setReplayMode((prev) => {
                  const next = !prev;
                  if (next) {
                    inspectorSuppressedRef.current = false;
                  }
                  return next;
                });
                setReplayGraph(null);
              }}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
                replayMode
                  ? 'border-[#0257D5] bg-[#EFF6FF] text-[#041533] dark:border-[#00C2FF] dark:bg-[#0257D5]/25 dark:text-white'
                  : 'border-[#D4E2F4] bg-white text-[#061838] hover:bg-[#F5F9FF] dark:border-[#1D3868] dark:bg-[#0A1B3B] dark:text-slate-200 dark:hover:bg-[#102650]',
              )}
            >
              <History className="h-3.5 w-3.5" aria-hidden="true" />
              <span>{replayMode ? 'Replay Active' : 'Replay Execution'}</span>
            </button>

            <button
              type="button"
              onClick={() => void loadRunData()}
              className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <RunAlertsBanner
        alerts={alerts}
        onFocusSpan={handleFocusSpan}
        onAcknowledgeAlert={handleAckAlert}
      />

      {replayMode && graph && (
        <TimelineReplay
          allNodes={graph.nodes}
          allEdges={graph.edges}
          onReplayFrame={handleReplayFrame}
          onExitReplay={() => {
            setReplayMode(false);
            setReplayGraph(null);
          }}
        />
      )}

      {loading ? (
        <div className="h-[560px] rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] flex items-center justify-center text-xs text-slate-500 dark:text-slate-400">
          Loading execution lineage graph...
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/40 p-10 text-center text-sm text-red-700 dark:text-red-300 space-y-3">
          <p className="font-semibold">Failed to load run</p>
          <p className="font-mono text-xs">{error}</p>
          <button
            type="button"
            onClick={() => void loadRunData()}
            className="rounded-md bg-red-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      ) : !activeGraph ? (
        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-10 text-center text-sm text-slate-600 dark:text-slate-400">
          Trace telemetry for <span className="font-mono">{decodedRunId}</span> was not found.
        </div>
      ) : viewMode === 'dag' ? (
        <LineageGraph
          graph={activeGraph}
          selectedSpanId={selectedSpan?.span_id}
          onSelectSpan={handleSelectSpan}
          impactedSpanIds={impactedSpanIds}
        />
      ) : (
        <WaterfallView
          nodes={activeGraph.nodes}
          selectedSpanId={selectedSpan?.span_id}
          impactedSpanIds={impactedSpanIds}
          onSelectSpan={handleSelectSpan}
        />
      )}

      <SpanInspector
        span={selectedSpan}
        traceId={run?.trace_id || graph?.trace_id}
        onClose={handleCloseInspector}
      />

      {mounted &&
        killModalOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setKillModalOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              className="w-full max-w-md rounded-lg border border-red-200 dark:border-red-800/80 bg-white dark:bg-[#07152E] p-5 shadow-xl space-y-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start gap-3">
                <OctagonAlert className="h-5 w-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Engage Emergency Kill-Switch?
                  </h3>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                    This immediately broadcasts an abort directive for run{' '}
                    <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">
                      {decodedRunId}
                    </span>{' '}
                    and marks in-flight spans as CANCELLED.
                  </p>
                </div>
              </div>
              {killError && (
                <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2.5 text-xs font-mono text-red-700 dark:text-red-300">
                  {killError}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                <button
                  type="button"
                  onClick={() => setKillModalOpen(false)}
                  className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-4 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={killing}
                  onClick={() => void handleKillRun()}
                  className="rounded-md bg-red-600 px-4 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {killing ? 'Aborting Run...' : 'Confirm Kill Run'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
