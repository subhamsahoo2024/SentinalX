'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import {
  Sliders,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Plus,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  X,
  Edit3,
  Bot,
  Users,
  Globe,
  Coins,
  Repeat,
  Zap,
  Tag,
  Lock,
} from 'lucide-react';
import { createPolicy, fetchPolicies, updatePolicy } from '@/lib/api';
import { cn } from '@/lib/cn';
import { PolicyCreateInput, PolicyDTO, PolicyUpdateInput } from '@/types/telemetry';

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

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyDTO[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  // Filter / Search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [scopeFilter, setScopeFilter] = useState<'ALL' | 'GLOBAL' | 'TEAM' | 'AGENT'>('ALL');

  // New Policy Modal
  const [showNewModal, setShowNewModal] = useState<boolean>(false);
  const [newScopeType, setNewScopeType] = useState<'global' | 'team' | 'agent'>('team');
  const [newName, setNewName] = useState<string>('');
  const [newTeam, setNewTeam] = useState<string>('');
  const [newAgentId, setNewAgentId] = useState<string>('');
  const [newMaxTokens, setNewMaxTokens] = useState<number>(5000);
  const [newMaxCostUsd, setNewMaxCostUsd] = useState<number>(0.5);
  const [newLoopThreshold, setNewLoopThreshold] = useState<number>(3);
  const [newLoopWindowSec, setNewLoopWindowSec] = useState<number>(30);
  const [newAutoBlock, setNewAutoBlock] = useState<boolean>(false);
  const [newProtectedTools, setNewProtectedTools] = useState<string>('restart_production_cluster');
  const [newEnabled, setNewEnabled] = useState<boolean>(true);
  const [submittingNew, setSubmittingNew] = useState<boolean>(false);
  const [newFormError, setNewFormError] = useState<string | null>(null);

  // Edit Thresholds Drawer / Modal
  const [editingPolicy, setEditingPolicy] = useState<PolicyDTO | null>(null);
  const [editName, setEditName] = useState<string>('');
  const [editMaxTokens, setEditMaxTokens] = useState<number>(5000);
  const [editMaxCostUsd, setEditMaxCostUsd] = useState<number>(0.5);
  const [editLoopThreshold, setEditLoopThreshold] = useState<number>(3);
  const [editLoopWindowSec, setEditLoopWindowSec] = useState<number>(30);
  const [editAutoBlock, setEditAutoBlock] = useState<boolean>(false);
  const [editProtectedTools, setEditProtectedTools] = useState<string>('');
  const [editEnabled, setEditEnabled] = useState<boolean>(true);
  const [savingEdit, setSavingEdit] = useState<boolean>(false);
  const [editFormError, setEditFormError] = useState<string | null>(null);

  // Toggling an individual policy inline
  const [togglingPolicyId, setTogglingPolicyId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setRefreshing(true);
      const data = await fetchPolicies();
      setPolicies(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load policies:', err);
      setError(err instanceof Error ? err.message : 'Failed to load governance policies');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleEnabled = async (policy: PolicyDTO) => {
    try {
      setTogglingPolicyId(policy.policy_id);
      const updated = await updatePolicy(policy.policy_id, {
        enabled: !policy.enabled,
      });
      setPolicies((prev) =>
        prev.map((p) => (p.policy_id === updated.policy_id ? updated : p))
      );
      setStatusMessage({
        type: 'success',
        text: `Policy "${policy.name}" ${updated.enabled ? 'enabled' : 'disabled'}.`,
      });
      setTimeout(() => setStatusMessage(null), 4000);
    } catch (err) {
      console.error('Failed to toggle policy state:', err);
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to update policy state',
      });
    } finally {
      setTogglingPolicyId(null);
    }
  };

  const handleOpenEdit = (policy: PolicyDTO) => {
    setEditingPolicy(policy);
    setEditName(policy.name);
    setEditMaxTokens(policy.max_tokens);
    setEditMaxCostUsd(policy.max_cost_usd);
    setEditLoopThreshold(policy.loop_threshold);
    setEditLoopWindowSec(policy.loop_window_sec);
    setEditAutoBlock(policy.auto_block_on_budget);
    setEditProtectedTools(policy.protected_tools.join(', '));
    setEditEnabled(policy.enabled);
    setEditFormError(null);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPolicy) return;
    try {
      setSavingEdit(true);
      setEditFormError(null);

      const parsedTools = editProtectedTools
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload: PolicyUpdateInput = {
        name: editName.trim() || undefined,
        max_tokens: Number(editMaxTokens),
        max_cost_usd: Number(editMaxCostUsd),
        loop_threshold: Number(editLoopThreshold),
        loop_window_sec: Number(editLoopWindowSec),
        auto_block_on_budget: editAutoBlock,
        protected_tools: parsedTools,
        enabled: editEnabled,
      };

      const updated = await updatePolicy(editingPolicy.policy_id, payload);
      setPolicies((prev) =>
        prev.map((p) => (p.policy_id === updated.policy_id ? updated : p))
      );
      setEditingPolicy(null);
      setStatusMessage({
        type: 'success',
        text: `Policy "${updated.name}" updated successfully.`,
      });
      setTimeout(() => setStatusMessage(null), 4000);
    } catch (err) {
      console.error('Failed to update policy:', err);
      setEditFormError(err instanceof Error ? err.message : 'Failed to update policy');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setNewFormError('Policy name is required.');
      return;
    }

    try {
      setSubmittingNew(true);
      setNewFormError(null);

      const parsedTools = newProtectedTools
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload: PolicyCreateInput = {
        name: newName.trim(),
        team: newScopeType === 'global' ? null : newTeam.trim() || null,
        agent_id: newScopeType === 'agent' ? newAgentId.trim() || null : null,
        max_tokens: Number(newMaxTokens),
        max_cost_usd: Number(newMaxCostUsd),
        loop_threshold: Number(newLoopThreshold),
        loop_window_sec: Number(newLoopWindowSec),
        auto_block_on_budget: newAutoBlock,
        protected_tools: parsedTools,
        enabled: newEnabled,
      };

      const created = await createPolicy(payload);
      setPolicies((prev) => [created, ...prev]);
      setShowNewModal(false);
      // Reset form
      setNewName('');
      setNewTeam('');
      setNewAgentId('');
      setNewMaxTokens(5000);
      setNewMaxCostUsd(0.5);
      setNewLoopThreshold(3);
      setNewLoopWindowSec(30);
      setNewAutoBlock(false);
      setNewProtectedTools('restart_production_cluster');
      setNewEnabled(true);

      setStatusMessage({
        type: 'success',
        text: `Policy "${created.name}" created successfully.`,
      });
      setTimeout(() => setStatusMessage(null), 4000);
    } catch (err) {
      console.error('Failed to create policy:', err);
      setNewFormError(err instanceof Error ? err.message : 'Failed to create policy');
    } finally {
      setSubmittingNew(false);
    }
  };

  // Filtered policies
  const filteredPolicies = policies.filter((p) => {
    const matchesSearch =
      searchQuery === '' ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.policy_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.team && p.team.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (p.agent_id && p.agent_id.toLowerCase().includes(searchQuery.toLowerCase()));

    if (!matchesSearch) return false;

    if (scopeFilter === 'GLOBAL') {
      return !p.team && !p.agent_id;
    }
    if (scopeFilter === 'TEAM') {
      return !!p.team && !p.agent_id;
    }
    if (scopeFilter === 'AGENT') {
      return !!p.agent_id;
    }
    return true;
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-cyan-950/80 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-sm shadow-cyan-950">
              <Sliders className="w-4 h-4 stroke-cyan-400" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Governance Policies
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            Define hierarchical runtime execution limits, tool loop anomaly thresholds, and budget circuit-breakers.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
            title="Refresh policies"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => {
              setNewFormError(null);
              setShowNewModal(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-mono font-semibold shadow-sm shadow-cyan-950 transition-colors"
          >
            <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
            <span>+ New Policy</span>
          </button>
        </div>
      </div>

      {/* Status or Error Notifications */}
      {statusMessage && (
        <div
          className={cn(
            'px-4 py-3 rounded-lg border text-xs font-mono flex items-center justify-between gap-3 animate-fadeIn',
            statusMessage.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
              : 'bg-rose-950/40 border-rose-500/30 text-rose-300'
          )}
        >
          <div className="flex items-center gap-2">
            {statusMessage.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{statusMessage.text}</span>
          </div>
          <button
            onClick={() => setStatusMessage(null)}
            className="text-slate-400 hover:text-white"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {error && (
        <div className="px-4 py-3 rounded-lg bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Error loading policies: {error}</span>
        </div>
      )}

      {/* Scope Priority Informational Callout */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono text-slate-400">
        <div className="flex items-start gap-2.5">
          <Shield className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
          <div>
            <span className="text-slate-200 font-semibold">Policy Resolution Priority: </span>
            <span className="text-purple-400 font-semibold">1. Agent-Specific</span>
            <span className="text-slate-500"> &rarr; </span>
            <span className="text-sky-400 font-semibold">2. Team-Specific</span>
            <span className="text-slate-500"> &rarr; </span>
            <span className="text-cyan-400 font-semibold">3. Global Default</span>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Sentinel-X evaluates runtime anomalies and circuit-breaker triggers against the most specific enabled policy match.
            </p>
          </div>
        </div>

        {/* Quick Filter Buttons */}
        <div className="flex items-center gap-1.5 self-start md:self-auto shrink-0">
          {(['ALL', 'GLOBAL', 'TEAM', 'AGENT'] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setScopeFilter(filter)}
              className={cn(
                'px-2.5 py-1 rounded-md text-[11px] font-mono transition-colors border',
                scopeFilter === filter
                  ? 'bg-slate-800 text-cyan-400 border-cyan-500/40'
                  : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200'
              )}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      {/* Policies Grid */}
      {loading ? (
        <div className="h-64 flex flex-col items-center justify-center gap-3 text-slate-400 font-mono text-xs">
          <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
          <span>Loading governance policies...</span>
        </div>
      ) : filteredPolicies.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center gap-2 border border-dashed border-slate-800 rounded-xl text-slate-500 font-mono text-xs">
          <Sliders className="w-6 h-6 stroke-slate-600 mb-1" />
          <span>No policies found matching current filters.</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPolicies.map((policy) => {
            const isAgentScoped = Boolean(policy.agent_id);
            const isTeamScoped = Boolean(policy.team) && !policy.agent_id;
            const isGlobal = !policy.team && !policy.agent_id;

            return (
              <div
                key={policy.policy_id}
                className={cn(
                  'rounded-xl border bg-slate-900/70 p-5 flex flex-col justify-between transition-all duration-150',
                  policy.enabled
                    ? 'border-slate-800 hover:border-slate-700/80 shadow-sm'
                    : 'border-slate-800/40 bg-slate-950/40 opacity-70'
                )}
              >
                <div>
                  {/* Top Scope Badge & Inline Toggle */}
                  <div className="flex items-center justify-between gap-2 mb-3">
                    {/* Scope Badge */}
                    {isAgentScoped ? (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-medium border bg-purple-500/10 text-purple-300 border-purple-500/30 flex items-center gap-1.5 truncate">
                        <Bot className="w-3 h-3 text-purple-400 shrink-0" />
                        <span className="truncate">Agent: {policy.agent_id}</span>
                      </span>
                    ) : isTeamScoped ? (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-medium border bg-sky-500/10 text-sky-300 border-sky-500/30 flex items-center gap-1.5 truncate">
                        <Users className="w-3 h-3 text-sky-400 shrink-0" />
                        <span className="truncate">Team: {policy.team}</span>
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-medium border bg-cyan-500/10 text-cyan-300 border-cyan-500/30 flex items-center gap-1.5">
                        <Globe className="w-3 h-3 text-cyan-400 shrink-0" />
                        <span>Global Default</span>
                      </span>
                    )}

                    {/* Inline Enable/Disable Toggle */}
                    <button
                      type="button"
                      onClick={() => handleToggleEnabled(policy)}
                      disabled={togglingPolicyId === policy.policy_id}
                      className={cn(
                        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-50',
                        policy.enabled ? 'bg-cyan-500' : 'bg-slate-700'
                      )}
                      title={policy.enabled ? 'Click to disable policy' : 'Click to enable policy'}
                    >
                      <span
                        className={cn(
                          'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-slate-950 shadow ring-0 transition duration-200 ease-in-out',
                          policy.enabled ? 'translate-x-4' : 'translate-x-0'
                        )}
                      />
                    </button>
                  </div>

                  {/* Policy Title & ID */}
                  <div className="mb-4">
                    <h3 className="text-sm font-bold text-slate-100 tracking-tight leading-snug">
                      {policy.name}
                    </h3>
                    <p className="text-[11px] font-mono text-slate-500 mt-0.5 truncate">
                      {policy.policy_id}
                    </p>
                  </div>

                  {/* Thresholds Metrics Grid */}
                  <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-4">
                    <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center gap-1 mb-1">
                        <Zap className="w-3 h-3 text-cyan-400" />
                        <span>Max Tokens</span>
                      </div>
                      <div className="text-slate-200 font-bold">
                        {policy.max_tokens.toLocaleString()}
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center gap-1 mb-1">
                        <Coins className="w-3 h-3 text-emerald-400" />
                        <span>Max Cost</span>
                      </div>
                      <div className="text-slate-200 font-bold">
                        ${Number(policy.max_cost_usd).toFixed(4)}
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center gap-1 mb-1">
                        <Repeat className="w-3 h-3 text-amber-400" />
                        <span>Loop Detection</span>
                      </div>
                      <div className="text-slate-200 font-bold">
                        {policy.loop_threshold} in {policy.loop_window_sec}s
                      </div>
                    </div>

                    <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold flex items-center gap-1 mb-1">
                        <Shield className="w-3 h-3 text-rose-400" />
                        <span>Circuit Breaker</span>
                      </div>
                      <div className="truncate">
                        {policy.auto_block_on_budget ? (
                          <span className="text-rose-400 font-bold">Auto-Block</span>
                        ) : (
                          <span className="text-slate-400 font-bold">Alert Only</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Protected Tools */}
                  {policy.protected_tools && policy.protected_tools.length > 0 && (
                    <div className="mb-4">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-mono font-semibold mb-1.5 flex items-center gap-1">
                        <Lock className="w-3 h-3 text-amber-400" />
                        <span>Protected Pre-Execution Tools</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {policy.protected_tools.map((tool) => (
                          <span
                            key={tool}
                            className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-950/90 text-amber-300 border border-amber-500/30"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Card Footer: Timestamp & Edit Button */}
                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono text-slate-500 mt-2">
                  <span title={formatDateTime(policy.updated_at)}>
                    Updated {formatRelativeTime(policy.updated_at)}
                  </span>

                  <button
                    onClick={() => handleOpenEdit(policy)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors text-xs font-mono"
                  >
                    <Edit3 className="w-3 h-3" />
                    <span>Edit Thresholds</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal: New Policy */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-xl shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-cyan-400" />
                <h2 className="text-sm font-bold text-slate-100 font-mono">
                  Create Governance Policy
                </h2>
              </div>
              <button
                onClick={() => setShowNewModal(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreatePolicy} className="p-5 space-y-4">
              {newFormError && (
                <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{newFormError}</span>
                </div>
              )}

              {/* Policy Scope Selector */}
              <div>
                <label className="block text-xs font-mono text-slate-300 mb-1.5 font-semibold">
                  Policy Scope
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setNewScopeType('global')}
                    className={cn(
                      'py-2 px-3 rounded-lg border text-xs font-mono text-center transition-colors',
                      newScopeType === 'global'
                        ? 'bg-cyan-500/10 border-cyan-500/40 text-cyan-300 font-semibold'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                    )}
                  >
                    Global Default
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewScopeType('team')}
                    className={cn(
                      'py-2 px-3 rounded-lg border text-xs font-mono text-center transition-colors',
                      newScopeType === 'team'
                        ? 'bg-sky-500/10 border-sky-500/40 text-sky-300 font-semibold'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                    )}
                  >
                    Team Specific
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewScopeType('agent')}
                    className={cn(
                      'py-2 px-3 rounded-lg border text-xs font-mono text-center transition-colors',
                      newScopeType === 'agent'
                        ? 'bg-purple-500/10 border-purple-500/40 text-purple-300 font-semibold'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                    )}
                  >
                    Agent Specific
                  </button>
                </div>
              </div>

              {/* Name */}
              <div>
                <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                  Policy Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Payments Hardened Circuit-Breaker Policy"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              {/* Team and Agent inputs based on scope */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {newScopeType !== 'global' && (
                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                      Team Name {newScopeType === 'team' ? '*' : '(Optional)'}
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. payments or platform"
                      value={newTeam}
                      onChange={(e) => setNewTeam(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 font-mono text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                )}

                {newScopeType === 'agent' && (
                  <div>
                    <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                      Target Agent ID *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. payment_auditor"
                      value={newAgentId}
                      onChange={(e) => setNewAgentId(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 font-mono text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                )}
              </div>

              {/* Budget Limits */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Max Tokens Ceiling
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={newMaxTokens}
                    onChange={(e) => setNewMaxTokens(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Max Cost Ceiling ($ USD)
                  </label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={newMaxCostUsd}
                    onChange={(e) => setNewMaxCostUsd(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Tool Loop Detection */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Loop Call Threshold
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={newLoopThreshold}
                    onChange={(e) => setNewLoopThreshold(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Loop Window (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={newLoopWindowSec}
                    onChange={(e) => setNewLoopWindowSec(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Protected Tools */}
              <div>
                <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                  Protected Tools (Comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="restart_production_cluster, drop_database"
                  value={newProtectedTools}
                  onChange={(e) => setNewProtectedTools(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 placeholder-slate-600 font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              {/* Switches: Auto-Block & Enabled */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newAutoBlock}
                    onChange={(e) => setNewAutoBlock(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
                  />
                  <div>
                    <div className="text-xs font-mono text-slate-200 font-semibold">Auto-Block Run</div>
                    <div className="text-[10px] font-mono text-slate-500">Trip circuit-breaker on budget breach</div>
                  </div>
                </label>

                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newEnabled}
                    onChange={(e) => setNewEnabled(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
                  />
                  <div>
                    <div className="text-xs font-mono text-slate-200 font-semibold">Enable Policy</div>
                    <div className="text-[10px] font-mono text-slate-500">Immediately enforce at runtime</div>
                  </div>
                </label>
              </div>

              {/* Submit Buttons */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowNewModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingNew}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-mono font-semibold transition-colors disabled:opacity-50"
                >
                  {submittingNew ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Creating...</span>
                    </>
                  ) : (
                    <span>Create Policy</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal / Drawer: Edit Thresholds */}
      {editingPolicy && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-cyan-400" />
                <h2 className="text-sm font-bold text-slate-100 font-mono">
                  Edit Governance Thresholds
                </h2>
              </div>
              <button
                onClick={() => setEditingPolicy(null)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="p-5 space-y-4">
              {editFormError && (
                <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{editFormError}</span>
                </div>
              )}

              {/* Policy Identification */}
              <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-xs font-mono">
                <span className="text-slate-500">Target ID: </span>
                <span className="text-cyan-400 font-bold">{editingPolicy.policy_id}</span>
                <div className="text-slate-400 mt-1">
                  Scope:{' '}
                  {editingPolicy.agent_id ? (
                    <span className="text-purple-300">Agent: {editingPolicy.agent_id}</span>
                  ) : editingPolicy.team ? (
                    <span className="text-sky-300">Team: {editingPolicy.team}</span>
                  ) : (
                    <span className="text-cyan-300">Global Default</span>
                  )}
                </div>
              </div>

              {/* Policy Name */}
              <div>
                <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                  Policy Name
                </label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              {/* Budget Limits */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Max Tokens Ceiling
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={editMaxTokens}
                    onChange={(e) => setEditMaxTokens(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Max Cost Ceiling ($ USD)
                  </label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={editMaxCostUsd}
                    onChange={(e) => setEditMaxCostUsd(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Tool Loop Detection */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Loop Call Threshold
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={editLoopThreshold}
                    onChange={(e) => setEditLoopThreshold(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                    Loop Window (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={editLoopWindowSec}
                    onChange={(e) => setEditLoopWindowSec(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              {/* Protected Tools */}
              <div>
                <label className="block text-xs font-mono text-slate-300 mb-1 font-semibold">
                  Protected Tools (Comma-separated)
                </label>
                <input
                  type="text"
                  value={editProtectedTools}
                  onChange={(e) => setEditProtectedTools(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              {/* Switches: Auto-Block & Enabled */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editAutoBlock}
                    onChange={(e) => setEditAutoBlock(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
                  />
                  <div>
                    <div className="text-xs font-mono text-slate-200 font-semibold">Auto-Block Run</div>
                    <div className="text-[10px] font-mono text-slate-500">Trip circuit-breaker on budget breach</div>
                  </div>
                </label>

                <label className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editEnabled}
                    onChange={(e) => setEditEnabled(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
                  />
                  <div>
                    <div className="text-xs font-mono text-slate-200 font-semibold">Enable Policy</div>
                    <div className="text-[10px] font-mono text-slate-500">Immediately enforce at runtime</div>
                  </div>
                </label>
              </div>

              {/* Submit Buttons */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setEditingPolicy(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-mono font-semibold transition-colors disabled:opacity-50"
                >
                  {savingEdit ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>Save Changes</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

