'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, Plus, Search, SlidersHorizontal, X } from 'lucide-react';
import { useIsClient } from '@/hooks/use-is-client';
import { createPolicy, fetchPolicies, updatePolicy } from '@/lib/api';
import { getStoredUser } from '@/lib/auth';
import { formatRelativeTime, formatTokens, formatUsd } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PolicyDTO } from '@/types/telemetry';

type ScopeFilter = 'ALL' | 'GLOBAL' | 'TEAM' | 'AGENT';
type CreateScope = 'global' | 'team' | 'agent';

function getPolicyScope(policy: PolicyDTO): 'AGENT' | 'TEAM' | 'GLOBAL' {
  if (policy.agent_id) return 'AGENT';
  if (policy.team) return 'TEAM';
  return 'GLOBAL';
}

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyDTO[]>([]);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const mounted = useIsClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<PolicyDTO | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);

  const [cScope, setCScope] = useState<CreateScope>('global');
  const [cName, setCName] = useState('');
  const [cTeam, setCTeam] = useState('it-ops');
  const [cAgentId, setCAgentId] = useState('');
  const [cMaxTokens, setCMaxTokens] = useState('10000');
  const [cMaxCost, setCMaxCost] = useState('1.00');
  const [cLoopThreshold, setCLoopThreshold] = useState('3');
  const [cLoopWindow, setCLoopWindow] = useState('30');
  const [cProtectedTools, setCProtectedTools] = useState('restart_production_cluster');
  const [cAutoBlock, setCAutoBlock] = useState(true);
  const [cEnabled, setCEnabled] = useState(true);

  const [eName, setEName] = useState('');
  const [eMaxTokens, setEMaxTokens] = useState('');
  const [eMaxCost, setEMaxCost] = useState('');
  const [eLoopThreshold, setELoopThreshold] = useState('');
  const [eLoopWindow, setELoopWindow] = useState('');
  const [eProtectedTools, setEProtectedTools] = useState('');
  const [eAutoBlock, setEAutoBlock] = useState(false);
  const [eEnabled, setEEnabled] = useState(true);

  const loadPolicies = useCallback(async () => {
    try {
      const data = await fetchPolicies();
      setPolicies(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load governance policies');
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadPolicies();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadPolicies]);

  const filteredPolicies = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return policies.filter((p) => {
      const scope = getPolicyScope(p);
      if (scopeFilter !== 'ALL' && scope !== scopeFilter) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        (p.team ?? '').toLowerCase().includes(q) ||
        (p.agent_id ?? '').toLowerCase().includes(q)
      );
    });
  }, [policies, scopeFilter, searchQuery]);

  const getActorRole = () => getStoredUser()?.role || 'approver';

  const handleToggleEnabled = async (policy: PolicyDTO) => {
    try {
      const updated = await updatePolicy(
        policy.policy_id,
        { enabled: !policy.enabled },
        getActorRole(),
      );
      setPolicies((prev) =>
        prev.map((p) => (p.policy_id === policy.policy_id ? updated : p)),
      );
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to toggle policy');
    }
  };

  const openEdit = (policy: PolicyDTO) => {
    setModalError(null);
    setEditingPolicy(policy);
    setEName(policy.name);
    setEMaxTokens(String(policy.max_tokens));
    setEMaxCost(String(policy.max_cost_usd));
    setELoopThreshold(String(policy.loop_threshold));
    setELoopWindow(String(policy.loop_window_sec));
    setEProtectedTools(policy.protected_tools.join(', '));
    setEAutoBlock(policy.auto_block_on_budget);
    setEEnabled(policy.enabled);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cName.trim()) return;
    setModalError(null);
    const tools = cProtectedTools
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      await createPolicy(
        {
          name: cName.trim(),
          team: cScope === 'team' ? cTeam.trim() : null,
          agent_id: cScope === 'agent' ? cAgentId.trim() : null,
          max_tokens: Number(cMaxTokens) || 10000,
          max_cost_usd: Number(cMaxCost) || 1.0,
          loop_threshold: Number(cLoopThreshold) || 3,
          loop_window_sec: Number(cLoopWindow) || 30,
          protected_tools: tools,
          auto_block_on_budget: cAutoBlock,
          enabled: cEnabled,
        },
        getActorRole(),
      );
      setCName('');
      setCreateOpen(false);
      await loadPolicies();
    } catch (err: unknown) {
      setModalError(err instanceof Error ? err.message : 'Failed to create policy');
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPolicy) return;
    setModalError(null);
    const tools = eProtectedTools
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      await updatePolicy(
        editingPolicy.policy_id,
        {
          name: eName.trim(),
          max_tokens: Number(eMaxTokens) || 10000,
          max_cost_usd: Number(eMaxCost) || 1.0,
          loop_threshold: Number(eLoopThreshold) || 3,
          loop_window_sec: Number(eLoopWindow) || 30,
          protected_tools: tools,
          auto_block_on_budget: eAutoBlock,
          enabled: eEnabled,
        },
        getActorRole(),
      );
      setEditingPolicy(null);
      await loadPolicies();
    } catch (err: unknown) {
      setModalError(err instanceof Error ? err.message : 'Failed to update policy');
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Governance Policies & Guardrails
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Scope resolution priority: 1. Agent-Specific &rarr; 2. Team-Specific &rarr; 3. Global Default.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setModalError(null);
            setCreateOpen(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] transition-colors whitespace-nowrap shrink-0"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          <span>New Policy</span>
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="inline-flex items-center gap-1 rounded-lg bg-slate-100 dark:bg-[#0A1B3B] border border-transparent dark:border-[#172E56] p-1 self-start">
          {(['ALL', 'GLOBAL', 'TEAM', 'AGENT'] as ScopeFilter[]).map((scope) => (
            <button
              key={scope}
              type="button"
              onClick={() => setScopeFilter(scope)}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap',
                scopeFilter === scope
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-[#0257D5] dark:text-white'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
              )}
            >
              {scope}
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
            placeholder="Search policy, team, or agent..."
            aria-label="Search policies"
            className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#07152E] pl-8 pr-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
          />
        </div>
      </div>

      {filteredPolicies.length === 0 ? (
        <div className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-center text-xs text-slate-500 dark:text-slate-400">
          No governance policies match your filter criteria.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredPolicies.map((policy) => {
            const scope = getPolicyScope(policy);
            const scopeLabel =
              scope === 'AGENT'
                ? `Agent: ${policy.agent_id}`
                : scope === 'TEAM'
                  ? `Team: ${policy.team}`
                  : 'Global Default';

            return (
              <article
                key={policy.policy_id}
                className="rounded-lg border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-5 space-y-4 flex flex-col justify-between"
              >
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                          {policy.name}
                        </h3>
                        <span className="rounded border border-slate-200 dark:border-[#1D3868] bg-slate-50 dark:bg-[#0A1B3B] px-2 py-0.5 font-mono text-[11px] text-slate-700 dark:text-[#7DD3FC]">
                          {scopeLabel}
                        </span>
                      </div>
                      <p className="mt-1 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                        {policy.policy_id}
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={policy.enabled}
                      onClick={() => void handleToggleEnabled(policy)}
                      className={cn(
                        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0257D5]',
                        policy.enabled ? 'bg-emerald-600' : 'bg-slate-300 dark:bg-slate-700',
                      )}
                      aria-label={`Toggle ${policy.name}`}
                    >
                      <span
                        className={cn(
                          'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform',
                          policy.enabled ? 'translate-x-4' : 'translate-x-0',
                        )}
                      />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-t border-b border-slate-100 dark:border-[#172E56] py-3 text-xs">
                    <div>
                      <p className="text-slate-500 dark:text-slate-400">Max Tokens</p>
                      <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                        {formatTokens(policy.max_tokens)}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-500 dark:text-slate-400">Max Cost</p>
                      <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                        {formatUsd(policy.max_cost_usd, 2)}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-500 dark:text-slate-400">Loop Threshold</p>
                      <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                        {policy.loop_threshold} / {policy.loop_window_sec}s
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-500 dark:text-slate-400">Circuit Breaker</p>
                      <p
                        className={cn(
                          'mt-0.5 font-medium',
                          policy.auto_block_on_budget
                            ? 'text-red-700 dark:text-red-400'
                            : 'text-amber-700 dark:text-amber-400',
                        )}
                      >
                        {policy.auto_block_on_budget ? 'Auto-Block' : 'Alert Only'}
                      </p>
                    </div>
                  </div>

                  <div>
                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                      Protected HITL Tools
                    </p>
                    {policy.protected_tools.length === 0 ? (
                      <p className="text-xs text-slate-400 dark:text-slate-500">None configured</p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {policy.protected_tools.map((tool) => (
                          <span
                            key={tool}
                            className="rounded border border-amber-200 dark:border-amber-800/80 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 font-mono text-[11px] text-amber-900 dark:text-amber-300"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>Updated {formatRelativeTime(policy.updated_at)}</span>
                  <button
                    type="button"
                    onClick={() => openEdit(policy)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-1.5 text-xs font-medium text-slate-800 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650] transition-colors"
                  >
                    <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Edit Thresholds</span>
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {mounted &&
        createOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setCreateOpen(false)}
          >
            <form
              onSubmit={handleCreateSubmit}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-lg rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl overflow-hidden"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  Create Governance Policy
                </h3>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="rounded p-1 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto text-xs">
                {modalError && (
                  <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2.5 text-xs font-mono text-red-700 dark:text-red-300 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span>{modalError}</span>
                  </div>
                )}

                <div>
                  <span className="block font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Policy Scope
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    {(['global', 'team', 'agent'] as CreateScope[]).map((sc) => (
                      <button
                        key={sc}
                        type="button"
                        onClick={() => setCScope(sc)}
                        className={cn(
                          'rounded-md border py-2 font-medium capitalize transition-colors',
                          cScope === sc
                            ? 'border-[#0257D5] bg-[#EFF6FF] text-[#041533] dark:border-[#00C2FF] dark:bg-[#0257D5]/25 dark:text-white'
                            : 'border-[#D4E2F4] text-slate-700 hover:bg-[#F5F9FF] dark:border-[#172E56] dark:text-slate-300 dark:hover:bg-[#0A1B3B]',
                        )}
                      >
                        {sc}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Policy Name
                  </label>
                  <input
                    type="text"
                    required
                    value={cName}
                    onChange={(e) => setCName(e.target.value)}
                    placeholder="e.g. Sec-Ops Strict Budget Guardrail"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                {cScope === 'team' && (
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Team Name
                    </label>
                    <input
                      type="text"
                      required
                      value={cTeam}
                      onChange={(e) => setCTeam(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                )}

                {cScope === 'agent' && (
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Agent ID
                    </label>
                    <input
                      type="text"
                      required
                      value={cAgentId}
                      onChange={(e) => setCAgentId(e.target.value)}
                      placeholder="agent-diagnostic"
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={cMaxTokens}
                      onChange={(e) => setCMaxTokens(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Max Cost ($ USD)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={cMaxCost}
                      onChange={(e) => setCMaxCost(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Loop Threshold (calls)
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={cLoopThreshold}
                      onChange={(e) => setCLoopThreshold(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Loop Window (sec)
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={cLoopWindow}
                      onChange={(e) => setCLoopWindow(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Protected Tools (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={cProtectedTools}
                    onChange={(e) => setCProtectedTools(e.target.value)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-6 pt-1">
                  <label className="inline-flex items-center gap-2 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={cAutoBlock}
                      onChange={(e) => setCAutoBlock(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#0257D5]"
                    />
                    <span>Auto-block run on budget</span>
                  </label>
                  <label className="inline-flex items-center gap-2 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={cEnabled}
                      onChange={(e) => setCEnabled(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#0257D5]"
                    />
                    <span>Enable policy</span>
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#040B18] px-5 py-3.5">
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-4 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0]"
                >
                  Create Policy
                </button>
              </div>
            </form>
          </div>,
          document.body,
        )}

      {mounted &&
        editingPolicy &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setEditingPolicy(null)}
          >
            <form
              onSubmit={handleEditSubmit}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-lg rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl overflow-hidden"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Edit Policy Thresholds
                  </h3>
                  <p className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                    {editingPolicy.policy_id}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingPolicy(null)}
                  className="rounded p-1 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="p-5 space-y-4 text-xs">
                {modalError && (
                  <div className="rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-2.5 text-xs font-mono text-red-700 dark:text-red-300 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span>{modalError}</span>
                  </div>
                )}

                <div>
                  <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Policy Name
                  </label>
                  <input
                    type="text"
                    required
                    value={eName}
                    onChange={(e) => setEName(e.target.value)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={eMaxTokens}
                      onChange={(e) => setEMaxTokens(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Max Cost ($ USD)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={eMaxCost}
                      onChange={(e) => setEMaxCost(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Loop Threshold (calls)
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={eLoopThreshold}
                      onChange={(e) => setELoopThreshold(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Loop Window (sec)
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={eLoopWindow}
                      onChange={(e) => setELoopWindow(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Protected Tools (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={eProtectedTools}
                    onChange={(e) => setEProtectedTools(e.target.value)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 font-mono text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-6 pt-1">
                  <label className="inline-flex items-center gap-2 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={eAutoBlock}
                      onChange={(e) => setEAutoBlock(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#0257D5]"
                    />
                    <span>Auto-block run on budget</span>
                  </label>
                  <label className="inline-flex items-center gap-2 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={eEnabled}
                      onChange={(e) => setEEnabled(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#0257D5]"
                    />
                    <span>Policy enabled</span>
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-200 dark:border-[#172E56] bg-slate-50 dark:bg-[#040B18] px-5 py-3.5">
                <button
                  type="button"
                  onClick={() => setEditingPolicy(null)}
                  className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-4 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0]"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>,
          document.body,
        )}
    </div>
  );
}
