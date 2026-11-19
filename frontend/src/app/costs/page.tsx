'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { format, formatDistanceToNow } from 'date-fns';
import {
  Coins,
  DollarSign,
  Layers,
  AlertTriangle,
  CheckCircle2,
  Plus,
  RefreshCw,
  Bot,
  Cpu,
  Users,
  Play,
  ArrowUpRight,
  Lock,
  Tag,
  AlertCircle,
} from 'lucide-react';
import {
  createPricingVersion,
  fetchCostSummary,
  fetchPricingVersions,
} from '@/lib/api';
import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import { cn } from '@/lib/cn';
import {
  CostBreakdownItemDTO,
  CostSummaryDTO,
  PricingVersionCreate,
  PricingVersionDTO,
} from '@/types/telemetry';

type BreakdownTab = 'agent' | 'team' | 'model' | 'run';

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return format(d, 'yyyy-MM-dd HH:mm:ss');
  } catch {
    return dateStr;
  }
}

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return dateStr;
  }
}

export default function CostsPage() {
  const [summary, setSummary] = useState<CostSummaryDTO | null>(null);
  const [pricingVersions, setPricingVersions] = useState<PricingVersionDTO[]>([]);
  const [activeTab, setActiveTab] = useState<BreakdownTab>('agent');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Inline Add Rate Form state
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [formProvider, setFormProvider] = useState<string>('openai');
  const [customProvider, setCustomProvider] = useState<string>('');
  const [formModelName, setFormModelName] = useState<string>('');
  const [formVersionTag, setFormVersionTag] = useState<string>('2026-11-v2');
  const [formInputRate, setFormInputRate] = useState<string>('2.50');
  const [formOutputRate, setFormOutputRate] = useState<string>('10.00');
  const [formActorRole, setFormActorRole] = useState<string>('approver');
  const [submittingRate, setSubmittingRate] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setRefreshing(true);
      const [sumData, pricingData] = await Promise.all([
        fetchCostSummary(),
        fetchPricingVersions(),
      ]);
      setSummary(sumData);
      setPricingVersions(pricingData);
      setError(null);
    } catch (err) {
      console.error('Failed to load costs data:', err);
      setError(
        err instanceof Error ? err.message : 'Failed to load cost data'
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial fetch: promise resolution avoids synchronous setState in effect body
  useEffect(() => {
    let isMounted = true;
    Promise.all([fetchCostSummary(), fetchPricingVersions()])
      .then(([sumData, pricingData]) => {
        if (!isMounted) return;
        setSummary(sumData);
        setPricingVersions(pricingData);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(
          err instanceof Error ? err.message : 'Failed to load cost data'
        );
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Live WebSocket streaming refresh on fleet update
  const handleWsMessage = useCallback(
    (msg: { type?: string }) => {
      if (
        msg?.type === 'SPAN_UPSERT' ||
        msg?.type === 'RUN_UPDATED' ||
        msg?.type === 'FLEET_UPDATED'
      ) {
        loadData();
      }
    },
    [loadData]
  );

  useWebSocketStream('/ws/fleet', handleWsMessage);

  // Submit new pricing version
  const handlePublishRate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    const provider =
      formProvider === 'other' ? customProvider.trim() : formProvider.trim();
    const modelName = formModelName.trim();
    const versionTag = formVersionTag.trim();
    const inRate = parseFloat(formInputRate);
    const outRate = parseFloat(formOutputRate);

    if (!provider) {
      setFormError('Provider is required.');
      return;
    }
    if (!modelName) {
      setFormError('Model name is required.');
      return;
    }
    if (!versionTag) {
      setFormError('Version tag is required.');
      return;
    }
    if (isNaN(inRate) || inRate < 0) {
      setFormError('Input rate must be a non-negative number.');
      return;
    }
    if (isNaN(outRate) || outRate < 0) {
      setFormError('Output rate must be a non-negative number.');
      return;
    }

    const payload: PricingVersionCreate = {
      provider,
      model_name: modelName,
      version_tag: versionTag,
      input_rate_per_1m: inRate,
      output_rate_per_1m: outRate,
    };

    try {
      setSubmittingRate(true);
      const created = await createPricingVersion(payload, formActorRole);
      setFormSuccess(
        `Successfully published rate for ${created.provider}/${created.model_name} (${created.version_tag})`
      );
      setFormModelName('');
      // Refresh pricing list and summary
      await loadData();
      setTimeout(() => setFormSuccess(null), 4000);
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : 'Failed to publish pricing version'
      );
    } finally {
      setSubmittingRate(false);
    }
  };

  // Active breakdown items based on tab
  const activeItems: CostBreakdownItemDTO[] = React.useMemo(() => {
    if (!summary) return [];
    let list: CostBreakdownItemDTO[] = [];
    if (activeTab === 'agent') list = summary.by_agent;
    else if (activeTab === 'team') list = summary.by_team;
    else if (activeTab === 'model') list = summary.by_model;
    else if (activeTab === 'run') list = summary.by_run;

    if (!searchTerm.trim()) return list;
    const q = searchTerm.toLowerCase();
    return list.filter(
      (item) =>
        item.key.toLowerCase().includes(q) ||
        item.label.toLowerCase().includes(q)
    );
  }, [summary, activeTab, searchTerm]);

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-sm shadow-cyan-950">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
                Cost & Token Attribution
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Versioned LLM pricing, token accounting, and chronological spend attribution
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={loadData}
            disabled={refreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-mono font-medium bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-300 hover:text-slate-100 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw
              className={cn('w-3.5 h-3.5 text-cyan-400', refreshing && 'animate-spin')}
            />
            <span>{refreshing ? 'Refreshing...' : 'Refresh Summary'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-3">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Top KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Recorded Spend */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Total Recorded Spend</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400 tracking-tight">
            ${summary ? summary.total_known_cost_usd.toFixed(4) : '0.0000'}
          </div>
          <p className="text-[11px] text-slate-400">
            Attributed across all completed leaf spans
          </p>
        </div>

        {/* Card 2: Total Tokens Processed */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Total Tokens Processed</span>
            <Coins className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-slate-100 tracking-tight">
            {summary ? summary.total_tokens.toLocaleString() : '0'}
          </div>
          <p className="text-[11px] text-slate-400">
            Input & completion token consumption
          </p>
        </div>

        {/* Card 3: Unknown-Usage Spans */}
        <div
          className={cn(
            'p-4 rounded-xl border space-y-1.5 shadow-sm transition-colors',
            summary && summary.unknown_usage_spans_count > 0
              ? 'bg-amber-950/20 border-amber-500/40'
              : 'bg-slate-900/60 border-slate-800/80'
          )}
        >
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Unknown-Usage Spans</span>
            {summary && summary.unknown_usage_spans_count > 0 ? (
              <AlertTriangle className="w-4 h-4 text-amber-400 animate-pulse" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            )}
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'text-2xl font-bold font-mono tracking-tight',
                summary && summary.unknown_usage_spans_count > 0
                  ? 'text-amber-400'
                  : 'text-slate-100'
              )}
            >
              {summary ? summary.unknown_usage_spans_count : 0}
            </span>
            {summary && summary.unknown_usage_spans_count > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                ATTN REQUIRED
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-400">
            {summary && summary.unknown_usage_spans_count > 0
              ? 'Missing provider token metadata or rate'
              : 'All leaf span costs attributed accurately'}
          </p>
        </div>

        {/* Card 4: Active Pricing Versions */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1.5 shadow-sm">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Active Model Rates</span>
            <Layers className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-indigo-400 tracking-tight">
            {pricingVersions.length}
          </div>
          <p className="text-[11px] text-slate-400">
            Configured provider pricing tiers
          </p>
        </div>
      </div>

      {/* Breakdown Tabs & Table Section */}
      <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 shadow-md overflow-hidden flex flex-col">
        {/* Section Header & Tab Controls */}
        <div className="p-4 sm:p-5 border-b border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-slate-950/40">
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <span>Cost Breakdown & Attribution</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Aggregated token consumption and financial spend by slice
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Tab Buttons */}
            <div className="inline-flex p-1 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
              <button
                type="button"
                onClick={() => {
                  setActiveTab('agent');
                  setSearchTerm('');
                }}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors',
                  activeTab === 'agent'
                    ? 'bg-slate-800 text-slate-100 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                <Bot className="w-3.5 h-3.5 text-indigo-400" />
                <span>By Agent</span>
                <span className="text-[10px] text-slate-500 font-normal">
                  ({summary?.by_agent.length || 0})
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setActiveTab('team');
                  setSearchTerm('');
                }}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors',
                  activeTab === 'team'
                    ? 'bg-slate-800 text-slate-100 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                <Users className="w-3.5 h-3.5 text-cyan-400" />
                <span>By Team</span>
                <span className="text-[10px] text-slate-500 font-normal">
                  ({summary?.by_team.length || 0})
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setActiveTab('model');
                  setSearchTerm('');
                }}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors',
                  activeTab === 'model'
                    ? 'bg-slate-800 text-slate-100 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                <span>By Model</span>
                <span className="text-[10px] text-slate-500 font-normal">
                  ({summary?.by_model.length || 0})
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setActiveTab('run');
                  setSearchTerm('');
                }}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors',
                  activeTab === 'run'
                    ? 'bg-slate-800 text-slate-100 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                )}
              >
                <Play className="w-3.5 h-3.5 text-emerald-400" />
                <span>By Run</span>
                <span className="text-[10px] text-slate-500 font-normal">
                  ({summary?.by_run.length || 0})
                </span>
              </button>
            </div>

            {/* Quick Filter Input */}
            <input
              type="text"
              placeholder={`Filter by ${activeTab}...`}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500 w-36 sm:w-48"
            />
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-slate-950/70 border-b border-slate-800 text-[11px] text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">
                  {activeTab === 'agent'
                    ? 'Agent Identifier'
                    : activeTab === 'team'
                    ? 'Team'
                    : activeTab === 'model'
                    ? 'Model'
                    : 'Run ID'}
                </th>
                <th className="py-3 px-4">Runs</th>
                <th className="py-3 px-4">Spans</th>
                <th className="py-3 px-4">Input Tokens</th>
                <th className="py-3 px-4">Output Tokens</th>
                <th className="py-3 px-4">Total Tokens</th>
                <th className="py-3 px-4">Unknown Spans</th>
                <th className="py-3 px-4 text-right">Attributed Spend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    <RefreshCw className="w-5 h-5 mx-auto animate-spin text-cyan-400 mb-2" />
                    <span>Loading attribution metrics...</span>
                  </td>
                </tr>
              ) : activeItems.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    No breakdown entries found for this category.
                  </td>
                </tr>
              ) : (
                activeItems.map((item) => {
                  const totalTokens = item.input_tokens + item.output_tokens;
                  return (
                    <tr
                      key={item.key}
                      className="hover:bg-slate-800/30 transition-colors"
                    >
                      <td className="py-3 px-4 font-semibold text-slate-100">
                        {activeTab === 'run' ? (
                          <Link
                            href={`/runs/${encodeURIComponent(item.key)}`}
                            className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 hover:underline"
                            title={`Inspect Run ${item.key}`}
                          >
                            <span>Run: {item.key}</span>
                            <ArrowUpRight className="w-3.5 h-3.5" />
                          </Link>
                        ) : (
                          <div className="flex flex-col">
                            <span>{item.label}</span>
                            {item.label !== item.key && (
                              <span className="text-[10px] text-slate-500">
                                {item.key}
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4">{item.run_count}</td>
                      <td className="py-3 px-4">{item.span_count}</td>
                      <td className="py-3 px-4 text-slate-400">
                        {item.input_tokens.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {item.output_tokens.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-200">
                        {totalTokens.toLocaleString()}
                      </td>
                      <td className="py-3 px-4">
                        {item.unknown_spans_count > 0 ? (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30"
                            title="Missing token metrics or unconfigured model pricing"
                          >
                            <AlertTriangle className="w-3 h-3 text-amber-400" />
                            {item.unknown_spans_count} unknown
                          </span>
                        ) : (
                          <span className="text-slate-500">0</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right font-bold">
                        {item.total_cost_usd !== null && item.total_cost_usd !== undefined ? (
                          <span className="text-emerald-400">
                            ${Number(item.total_cost_usd).toFixed(4)}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
                            Unknown
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Versioned Pricing Table & Inline Add Rate Form */}
      <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 shadow-md overflow-hidden flex flex-col space-y-4 p-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Tag className="w-4 h-4 text-indigo-400" />
              <span>Versioned Model Rates</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Active token rates used by SentinelX for exact leaf span spend attribution
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowAddForm((prev) => !prev)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{showAddForm ? 'Cancel Add Rate' : 'Add Model Rate'}</span>
          </button>
        </div>

        {/* Inline Add Rate Form */}
        {showAddForm && (
          <form
            onSubmit={handlePublishRate}
            className="p-4 rounded-xl bg-slate-950/80 border border-indigo-500/30 space-y-4"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-300 font-mono flex items-center gap-1.5">
                <Plus className="w-3.5 h-3.5" />
                Publish New Pricing Version
              </span>
              <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
                <Lock className="w-3 h-3 text-slate-400" />
                Approver/Admin Role Required
              </span>
            </div>

            {formError && (
              <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs font-mono">
                {formError}
              </div>
            )}

            {formSuccess && (
              <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs font-mono">
                {formSuccess}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* Provider select */}
              <div>
                <label className="block text-[11px] font-mono text-slate-400 mb-1">
                  Provider
                </label>
                <select
                  value={formProvider}
                  onChange={(e) => setFormProvider(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="openai">openai</option>
                  <option value="anthropic">anthropic</option>
                  <option value="google">google</option>
                  <option value="other">Other (Custom)</option>
                </select>
              </div>

              {/* Custom provider if "other" */}
              {formProvider === 'other' ? (
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    Custom Provider
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. cohere"
                    value={customProvider}
                    onChange={(e) => setCustomProvider(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    Model Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. gpt-4.5-preview"
                    value={formModelName}
                    onChange={(e) => setFormModelName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              )}

              {formProvider === 'other' && (
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    Model Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. command-r-plus"
                    value={formModelName}
                    onChange={(e) => setFormModelName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              )}

              {/* Version Tag */}
              <div>
                <label className="block text-[11px] font-mono text-slate-400 mb-1">
                  Version Tag
                </label>
                <input
                  type="text"
                  placeholder="2026-11-v2"
                  value={formVersionTag}
                  onChange={(e) => setFormVersionTag(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Input Rate per 1M */}
              <div>
                <label className="block text-[11px] font-mono text-slate-400 mb-1">
                  Input Rate ($ / 1M)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formInputRate}
                  onChange={(e) => setFormInputRate(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Output Rate per 1M */}
              <div>
                <label className="block text-[11px] font-mono text-slate-400 mb-1">
                  Output Rate ($ / 1M)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formOutputRate}
                  onChange={(e) => setFormOutputRate(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Actor Role */}
              <div>
                <label className="block text-[11px] font-mono text-slate-400 mb-1">
                  Actor Role
                </label>
                <select
                  value={formActorRole}
                  onChange={(e) => setFormActorRole(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="approver">approver (Authorized)</option>
                  <option value="admin">admin (Authorized)</option>
                  <option value="operator">operator (403 Forbidden)</option>
                  <option value="viewer">viewer (403 Forbidden)</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submittingRate}
                className="px-4 py-1.5 rounded-lg text-xs font-mono font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors disabled:opacity-50"
              >
                {submittingRate ? 'Publishing...' : 'Publish Rate'}
              </button>
            </div>
          </form>
        )}

        {/* Pricing Version Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-slate-950/70 border-b border-slate-800 text-[11px] text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Provider</th>
                <th className="py-3 px-4">Model Name</th>
                <th className="py-3 px-4">Version Tag</th>
                <th className="py-3 px-4">Input Rate ($ / 1M)</th>
                <th className="py-3 px-4">Output Rate ($ / 1M)</th>
                <th className="py-3 px-4">Effective From</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {pricingVersions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500">
                    No active pricing versions found.
                  </td>
                </tr>
              ) : (
                pricingVersions.map((pv) => (
                  <tr
                    key={pv.id}
                    className="hover:bg-slate-800/30 transition-colors"
                  >
                    <td className="py-3 px-4 font-semibold text-slate-100">
                      <span className="capitalize">{pv.provider}</span>
                    </td>
                    <td className="py-3 px-4 font-bold text-slate-200">
                      {pv.model_name}
                    </td>
                    <td className="py-3 px-4 text-slate-400">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 border border-slate-700">
                        {pv.version_tag}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-medium text-emerald-400">
                      ${pv.input_rate_per_1m.toFixed(2)}
                    </td>
                    <td className="py-3 px-4 font-medium text-emerald-400">
                      ${pv.output_rate_per_1m.toFixed(2)}
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      <div>{formatDateTime(pv.effective_from)}</div>
                      <div className="text-[10px] text-slate-500">
                        {formatRelativeTime(pv.effective_from)}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
