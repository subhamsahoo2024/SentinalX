'use client';

import { Suspense, use, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { fetchRunById } from '@/lib/api';
import { RunSummaryDTO } from '@/types/telemetry';

function RunDetailContent({ params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = use(params);
  const [run, setRun] = useState<RunSummaryDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    fetchRunById(run_id)
      .then((data) => {
        if (isMounted) {
          setRun(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load run details');
        }
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [run_id]);

  return (
    <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <Link
          href="/"
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight text-slate-100 font-mono">
              Run: {run_id}
            </h2>
            {run?.status && (
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                {run.status}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5 font-mono">
            Trace ID: {run?.trace_id || '—'}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-400 font-mono text-sm animate-pulse">
          Loading run telemetry...
        </div>
      ) : error ? (
        <div className="p-6 rounded-xl bg-rose-950/40 border border-rose-500/30 text-rose-300 text-sm">
          {error}
        </div>
      ) : run ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800">
            <div className="text-xs font-mono text-slate-400 uppercase">Agent</div>
            <div className="text-lg font-semibold text-slate-100 mt-2">
              {run.agent_name || run.agent_id}
            </div>
            <div className="text-xs font-mono text-slate-400 mt-1">team: {run.team}</div>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800">
            <div className="text-xs font-mono text-slate-400 uppercase">Duration</div>
            <div className="text-lg font-semibold text-slate-100 mt-2 font-mono">
              {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(2)}s` : '—'}
            </div>
            <div className="text-xs font-mono text-slate-400 mt-1">
              {run.total_spans ?? 0} spans
            </div>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800">
            <div className="text-xs font-mono text-slate-400 uppercase">Tokens</div>
            <div className="text-lg font-semibold text-slate-100 mt-2 font-mono">
              {run.total_tokens?.toLocaleString() ?? 0}
            </div>
            <div className="text-xs font-mono text-slate-400 mt-1">Total recorded</div>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/50 border border-slate-800">
            <div className="text-xs font-mono text-slate-400 uppercase">Cost</div>
            <div className="text-lg font-semibold text-slate-100 mt-2 font-mono">
              {run.total_cost_usd !== undefined && run.total_cost_usd !== null
                ? `$${Number(run.total_cost_usd).toFixed(4)}`
                : 'Unknown'}
            </div>
            <div className="text-xs font-mono text-slate-400 mt-1">USD basis</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ run_id: string }>;
}) {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-slate-400 font-mono text-sm">
          Loading run...
        </div>
      }
    >
      <RunDetailContent params={params} />
    </Suspense>
  );
}
