'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, Plus, Search, X } from 'lucide-react';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import {
  createPricingVersion,
  fetchCostSummary,
  fetchPricingVersions,
} from '@/lib/api';
import { getStoredUser } from '@/lib/auth';
import { formatTokens, formatUsd, formatUtcTimestamp } from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  ActorRole,
  CostBreakdownItemDTO,
  CostSummaryDTO,
  PricingVersionDTO,
  WebSocketMessage,
} from '@/types/telemetry';

type SliceTab = 'by_agent' | 'by_team' | 'by_model' | 'by_run';

const SLICE_TABS: { key: SliceTab; label: string }[] = [
  { key: 'by_agent', label: 'By Agent' },
  { key: 'by_team', label: 'By Team' },
  { key: 'by_model', label: 'By Model' },
  { key: 'by_run', label: 'By Run' },
];

export default function CostsPage() {
  const [summary, setSummary] = useState<CostSummaryDTO | null>(null);
  const [rates, setRates] = useState<PricingVersionDTO[]>([]);
  const [slice, setSlice] = useState<SliceTab>('by_agent');
  const [searchQuery, setSearchQuery] = useState('');
  const [showForm, setShowForm] = useState(false);

  const [provider, setProvider] = useState('openai');
  const [customProvider, setCustomProvider] = useState('');
  const [modelName, setModelName] = useState('');
  const [versionTag, setVersionTag] = useState('2026-11-v2');
  const [inputRate, setInputRate] = useState('2.50');
  const [outputRate, setOutputRate] = useState('10.00');
  const [actorRole, setActorRole] = useState<ActorRole>(() => {
    const r = getStoredUser()?.role;
    if (r === 'approver' || r === 'admin' || r === 'operator' || r === 'viewer') {
      return r;
    }
    return 'approver';
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [costData, pricingData] = await Promise.all([
        fetchCostSummary(),
        fetchPricingVersions(),
      ]);
      setSummary(costData);
      setRates(pricingData);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load cost attribution data');
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  const handleWsMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (
        msg.type === 'SPAN_UPSERT' ||
        msg.type === 'RUN_UPDATED' ||
        msg.type === 'FLEET_UPDATED'
      ) {
        void loadData();
      }
    },
    [loadData],
  );

  useWebSocketStream<WebSocketMessage>('/ws/fleet', handleWsMessage);

  const activeRows = useMemo<CostBreakdownItemDTO[]>(() => {
    if (!summary) return [];
    const raw = summary[slice] ?? [];
    const q = searchQuery.trim().toLowerCase();
    if (!q) return raw;
    return raw.filter(
      (item) =>
        item.key.toLowerCase().includes(q) || item.label.toLowerCase().includes(q),
    );
  }, [summary, slice, searchQuery]);

  const handleCreateRate = async (e: React.FormEvent) => {
    e.preventDefault();
    const resolvedProvider = provider === 'other' ? customProvider.trim() : provider;
    if (!resolvedProvider || !modelName.trim() || !versionTag.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await createPricingVersion(
        {
          provider: resolvedProvider,
          model_name: modelName.trim(),
          version_tag: versionTag.trim(),
          input_rate_per_1m: Number(inputRate) || 0,
          output_rate_per_1m: Number(outputRate) || 0,
        },
        actorRole,
      );
      setModelName('');
      setShowForm(false);
      await loadData();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Failed to publish pricing rate');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
          Cost & Token Attribution
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Subtree spend roll-ups across agents, teams, models, and versioned pricing tables.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Total Recorded Spend
          </p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-slate-900 dark:text-slate-100">
            {formatUsd(summary?.total_known_cost_usd)}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Total Tokens Processed
          </p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-slate-900 dark:text-slate-100">
            {formatTokens(summary?.total_tokens)}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Unknown-Usage Spans
          </p>
          <p
            className={cn(
              'mt-2 text-2xl font-semibold font-mono tabular-nums',
              (summary?.unknown_usage_spans_count ?? 0) > 0
                ? 'text-amber-700 dark:text-amber-400'
                : 'text-slate-900 dark:text-slate-100',
            )}
          >
            {summary?.unknown_usage_spans_count ?? 0}
          </p>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Active Model Rates
          </p>
          <p className="mt-2 text-2xl font-semibold font-mono tabular-nums text-slate-900 dark:text-slate-100">
            {rates.length}
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-[#0A1B3B] border border-transparent dark:border-[#172E56] p-1 self-start">
            {SLICE_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setSlice(tab.key)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap',
                  slice === tab.key
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0257D5] dark:text-white'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="relative w-full md:w-72">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400"
              aria-hidden="true"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter key or label..."
              aria-label="Filter cost breakdown"
              className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#07152E] pl-8 pr-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
            />
          </div>
        </div>

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#0A1B3B] text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                <th className="px-4 py-3">Key / Label</th>
                <th className="px-4 py-3 text-right">Runs</th>
                <th className="px-4 py-3 text-right">Spans</th>
                <th className="px-4 py-3 text-right">Input Tokens</th>
                <th className="px-4 py-3 text-right">Output Tokens</th>
                <th className="px-4 py-3 text-right">Total Tokens</th>
                <th className="px-4 py-3 text-right">Unknown Spans</th>
                <th className="px-4 py-3 text-right">Attributed Spend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#15284B] text-xs">
              {activeRows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    No attribution rows match your filter.
                  </td>
                </tr>
              ) : (
                activeRows.map((row) => {
                  const total = row.input_tokens + row.output_tokens;
                  return (
                    <tr
                      key={row.key}
                      className="hover:bg-slate-50 dark:hover:bg-[#0D2247] transition-colors"
                    >
                      <td className="px-4 py-3">
                        {slice === 'by_run' ? (
                          <Link
                            href={`/runs/${encodeURIComponent(row.key)}`}
                            className="font-mono font-medium text-[#0257D5] dark:text-[#38BDF8] hover:underline block"
                          >
                            {row.key}
                          </Link>
                        ) : (
                          <span className="font-mono font-medium text-slate-900 dark:text-slate-100 block">
                            {row.key}
                          </span>
                        )}
                        <span className="text-slate-500 dark:text-slate-400">{row.label}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {formatTokens(row.run_count)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {formatTokens(row.span_count)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {formatTokens(row.input_tokens)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {formatTokens(row.output_tokens)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums font-medium text-slate-900 dark:text-slate-100">
                        {formatTokens(total)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">
                        {row.unknown_spans_count}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums font-semibold text-slate-900 dark:text-slate-100">
                        {formatUsd(row.total_cost_usd)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Versioned Model Pricing Rates
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Effective rates per 1M input and output tokens used for cost attribution.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setFormError(null);
              setShowForm((s) => !s);
            }}
            className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] px-3.5 py-2 text-xs font-medium text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247] transition-colors whitespace-nowrap shrink-0"
          >
            {showForm ? (
              <>
                <X className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Cancel Add Rate</span>
              </>
            ) : (
              <>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Add Model Rate</span>
              </>
            )}
          </button>
        </div>

        {showForm && (
          <form
            onSubmit={handleCreateRate}
            className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-5 space-y-4"
          >
            {formError && (
              <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2.5 text-xs font-mono text-red-700 dark:text-red-300 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{formError}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Provider
                </label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                >
                  <option value="openai">openai</option>
                  <option value="anthropic">anthropic</option>
                  <option value="google">google</option>
                  <option value="other">other</option>
                </select>
              </div>

              {provider === 'other' && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Custom Provider
                  </label>
                  <input
                    type="text"
                    required
                    value={customProvider}
                    onChange={(e) => setCustomProvider(e.target.value)}
                    placeholder="e.g. mistral"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Model Name
                </label>
                <input
                  type="text"
                  required
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="e.g. gpt-4.5-preview"
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Version Tag
                </label>
                <input
                  type="text"
                  required
                  value={versionTag}
                  onChange={(e) => setVersionTag(e.target.value)}
                  placeholder="2026-11-v2"
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Input Rate ($ / 1M tokens)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={inputRate}
                  onChange={(e) => setInputRate(e.target.value)}
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Output Rate ($ / 1M tokens)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={outputRate}
                  onChange={(e) => setOutputRate(e.target.value)}
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Actor Role
                </label>
                <select
                  value={actorRole}
                  onChange={(e) => setActorRole(e.target.value as ActorRole)}
                  className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                >
                  <option value="approver">approver</option>
                  <option value="admin">admin</option>
                  <option value="operator">operator</option>
                  <option value="viewer">viewer</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={submitting}
                className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50 transition-colors"
              >
                {submitting ? 'Saving Rate...' : 'Publish Pricing Version'}
              </button>
            </div>
          </form>
        )}

        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#0A1B3B] text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Model Name</th>
                <th className="px-4 py-3">Version Tag</th>
                <th className="px-4 py-3 text-right">Input ($/1M)</th>
                <th className="px-4 py-3 text-right">Output ($/1M)</th>
                <th className="px-4 py-3 text-right">Effective From</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#15284B] text-xs">
              {rates.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    No active pricing versions found.
                  </td>
                </tr>
              ) : (
                rates.map((r) => (
                  <tr key={r.id}>
                    <td className="px-4 py-3 font-mono text-slate-700 dark:text-slate-300">
                      {r.provider}
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold text-slate-900 dark:text-slate-100">
                      {r.model_name}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">
                      {r.version_tag}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-900 dark:text-slate-100">
                      ${r.input_rate_per_1m.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-900 dark:text-slate-100">
                      ${r.output_rate_per_1m.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-500 dark:text-slate-400">
                      {formatUtcTimestamp(r.effective_from)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
