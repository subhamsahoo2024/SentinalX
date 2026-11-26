'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  KeyRound,
  Plus,
  Shield,
  ShieldAlert,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { useIsClient } from '@/hooks/use-is-client';
import {
  createApiKey,
  fetchApiKeys,
  fetchTeams,
  revokeApiKey,
} from '@/lib/api';
import { getAuthUserSnapshot, subscribeAuth } from '@/lib/auth';
import { formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ApiKeyCreatedDTO, ApiKeyDTO, TeamDTO } from '@/types/telemetry';

export default function ApiKeysPage() {
  const mounted = useIsClient();
  const currentUser = useSyncExternalStore(
    subscribeAuth,
    getAuthUserSnapshot,
    () => null,
  );
  const isOrgAdmin =
    currentUser?.role === 'admin' && currentUser?.is_demo !== true;

  const [apiKeys, setApiKeys] = useState<ApiKeyDTO[]>([]);
  const [teams, setTeams] = useState<TeamDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Mint API Key modal state
  const [mintOpen, setMintOpen] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [selectedTeam, setSelectedTeam] = useState('');
  const [minting, setMinting] = useState(false);
  const [mintError, setMintError] = useState<string | null>(null);

  // One-time raw secret reveal card state
  const [revealedKey, setRevealedKey] = useState<ApiKeyCreatedDTO | null>(null);
  const [copied, setCopied] = useState(false);

  // Revoke loading state
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const prodTeams = teams.filter((team) => team.team_id !== 'demo-sandbox');

  const loadData = useCallback(async () => {
    if (!isOrgAdmin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [keysData, teamsData] = await Promise.all([
        fetchApiKeys(),
        fetchTeams(),
      ]);
      setApiKeys(keysData);
      setTeams(teamsData);
      const nonSandboxTeams = teamsData.filter(
        (t) => t.team_id !== 'demo-sandbox',
      );
      setSelectedTeam((prev) =>
        prev || (nonSandboxTeams[0]?.team_id ?? ''),
      );
      setPageError(null);
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to load API keys',
      );
    } finally {
      setLoading(false);
    }
  }, [isOrgAdmin]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  const openMintModal = () => {
    setMintError(null);
    setKeyName('');
    setSelectedTeam((prev) => prev || (prodTeams[0]?.team_id ?? ''));
    setMintOpen(true);
  };

  const handleMintKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (minting) return;
    if (!keyName.trim() || !selectedTeam) {
      setMintError('Provide both a descriptive name and a target team.');
      return;
    }

    setMinting(true);
    setMintError(null);
    try {
      const created = await createApiKey({
        name: keyName.trim(),
        team: selectedTeam,
      });
      const summary: ApiKeyDTO = {
        key_id: created.key_id,
        name: created.name,
        team: created.team,
        key_prefix: created.key_prefix,
        created_by: created.created_by,
        last_used_at: created.last_used_at,
        revoked_at: created.revoked_at,
        created_at: created.created_at,
      };
      setApiKeys((prev) => [summary, ...prev]);
      setRevealedKey(created);
      setCopied(false);
      setMintOpen(false);
      setKeyName('');
    } catch (err: unknown) {
      setMintError(
        err instanceof Error ? err.message : 'Failed to mint API key',
      );
    } finally {
      setMinting(false);
    }
  };

  const handleCopySecret = async () => {
    if (!revealedKey) return;
    try {
      await navigator.clipboard.writeText(revealedKey.raw_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setPageError('Clipboard access failed. Please copy the secret manually.');
    }
  };

  const handleRevoke = async (keyId: string) => {
    if (revokingId) return;
    setRevokingId(keyId);
    setPageError(null);
    try {
      await revokeApiKey(keyId);
      const revokedIso = new Date().toISOString();
      setApiKeys((prev) =>
        prev.map((k) =>
          k.key_id === keyId ? { ...k, revoked_at: revokedIso } : k,
        ),
      );
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to revoke API key',
      );
    } finally {
      setRevokingId(null);
    }
  };

  if (mounted && currentUser && !isOrgAdmin) {
    return (
      <div className="rounded-xl border border-amber-300 dark:border-amber-700/60 bg-white dark:bg-[#07152E] p-8 max-w-xl">
        <div className="flex items-start gap-3">
          <Shield
            className="h-5 w-5 text-amber-500 shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Administrator Access Required
            </h2>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
              Only non-demo organization administrators can mint and revoke team-bound ingestion API keys.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {pageError && (
        <div className="rounded-lg border border-red-200 dark:border-red-800/70 bg-red-50 dark:bg-red-950/60 px-4 py-3 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{pageError}</span>
        </div>
      )}

      {/* One-Time Secret Reveal Card */}
      {revealedKey && (
        <section
          aria-live="polite"
          className="rounded-xl border border-emerald-300 dark:border-emerald-500/40 bg-emerald-50/70 dark:bg-[#061D29] shadow-sm overflow-hidden"
        >
          <div className="border-b border-emerald-200 dark:border-emerald-500/30 px-5 py-3.5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 min-w-0">
              <CheckCircle2
                className="h-4 w-4 text-emerald-600 dark:text-emerald-400 shrink-0"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-emerald-950 dark:text-emerald-200 truncate">
                  API Key Minted: {revealedKey.name}
                </h2>
                <p className="text-[11px] text-emerald-800 dark:text-emerald-300/80">
                  Bound to team{' '}
                  <span className="font-mono font-semibold">
                    {revealedKey.team}
                  </span>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setRevealedKey(null)}
              className="inline-flex items-center gap-1 rounded-md border border-emerald-300 dark:border-emerald-600/50 bg-white/80 dark:bg-[#07152E] px-2.5 py-1 text-xs font-medium text-emerald-900 dark:text-emerald-200 hover:bg-white dark:hover:bg-[#0A1F3D] transition-colors shrink-0"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Dismiss</span>
            </button>
          </div>

          <div className="p-5 space-y-3">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
              <code className="flex-1 rounded-lg border border-emerald-300 dark:border-emerald-500/35 bg-white dark:bg-[#030A17] px-3.5 py-2.5 text-xs font-mono text-slate-900 dark:text-emerald-300 break-all select-all">
                {revealedKey.raw_key}
              </code>
              <button
                type="button"
                onClick={() => void handleCopySecret()}
                className={cn(
                  'inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-xs font-medium transition-colors whitespace-nowrap shrink-0',
                  copied
                    ? 'bg-emerald-600 text-white'
                    : 'bg-[#0257D5] text-white hover:bg-[#0346B0]',
                )}
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Copy to Clipboard</span>
                  </>
                )}
              </button>
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-900 dark:text-amber-200">
              <ShieldAlert
                className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <p>
                Save this secret now. For security, Sentinel-X stores only a{' '}
                <span className="font-mono font-semibold">SHA-256</span> hash of
                this key and it cannot be viewed again once you dismiss this card.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Main API Keys Table Card */}
      <section className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-sm">
        <div className="border-b border-slate-200 dark:border-[#172E56] px-5 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <KeyRound
              className="h-4 w-4 text-[#0257D5] dark:text-[#00C2FF]"
              aria-hidden="true"
            />
            <div>
              <h2 className="text-sm font-semibold text-[#041533] dark:text-slate-100">
                Team Ingestion API Keys
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Telemetry ingested with a team key is server-stamped to that department namespace.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={openMintModal}
            className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3.5 py-2 text-xs font-medium text-white hover:bg-[#0346B0] transition-colors whitespace-nowrap"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Mint Team API Key</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-[#172E56] bg-slate-50/70 dark:bg-[#040B18] text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <th className="px-5 py-3">Key Name</th>
                <th className="px-5 py-3">Team</th>
                <th className="px-5 py-3">Key Prefix</th>
                <th className="px-5 py-3">Created By</th>
                <th className="px-5 py-3">Last Used</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-[#172E56] text-xs">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-5 py-8 text-center text-slate-500 dark:text-slate-400"
                  >
                    Loading team API keys...
                  </td>
                </tr>
              ) : apiKeys.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-5 py-8 text-center text-slate-500 dark:text-slate-400"
                  >
                    No team API keys minted yet. Click &quot;+ Mint Team API Key&quot; to create one.
                  </td>
                </tr>
              ) : (
                apiKeys.map((apiKey) => {
                  const isRevoked = apiKey.revoked_at !== null;
                  return (
                    <tr
                      key={apiKey.key_id}
                      className="hover:bg-[#F5F9FF]/60 dark:hover:bg-[#0A1B3B]/60 transition-colors"
                    >
                      <td className="px-5 py-3.5">
                        <p className="font-medium text-slate-900 dark:text-slate-100">
                          {apiKey.name}
                        </p>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          Created {formatRelativeTime(apiKey.created_at)}
                        </p>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="inline-flex rounded border border-[#93C5FD] dark:border-[#00C2FF]/40 bg-[#EFF6FF] dark:bg-[#0257D5]/25 px-2 py-0.5 text-[11px] font-mono text-[#0257D5] dark:text-[#7DD3FC]">
                          {apiKey.team}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-slate-700 dark:text-slate-300">
                        {apiKey.key_prefix}...
                      </td>
                      <td className="px-5 py-3.5 font-mono text-slate-700 dark:text-slate-300">
                        {apiKey.created_by}
                      </td>
                      <td className="px-5 py-3.5 text-slate-600 dark:text-slate-400">
                        {apiKey.last_used_at
                          ? formatRelativeTime(apiKey.last_used_at)
                          : 'Never'}
                      </td>
                      <td className="px-5 py-3.5">
                        {isRevoked ? (
                          <span className="inline-flex items-center gap-1 rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400">
                            <XCircle className="h-3 w-3" aria-hidden="true" />
                            <span>Revoked</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded border border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300">
                            <CheckCircle2
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                            <span>Active</span>
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        {isRevoked ? (
                          <span className="text-[11px] text-slate-400 dark:text-slate-500">
                            Revoked
                          </span>
                        ) : (
                          <button
                            type="button"
                            disabled={revokingId === apiKey.key_id}
                            onClick={() => void handleRevoke(apiKey.key_id)}
                            className="inline-flex items-center gap-1 rounded-md border border-red-200 dark:border-red-800/60 px-2.5 py-1 text-[11px] font-medium text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/50 disabled:opacity-50 transition-colors"
                          >
                            <Trash2 className="h-3 w-3" aria-hidden="true" />
                            <span>
                              {revokingId === apiKey.key_id
                                ? 'Revoking...'
                                : 'Revoke'}
                            </span>
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Mint Team API Key Modal */}
      {mounted &&
        mintOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setMintOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="mint-key-title"
              className="w-full max-w-md rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <h3
                  id="mint-key-title"
                  className="text-base font-semibold text-slate-900 dark:text-slate-100"
                >
                  Mint Team API Key
                </h3>
                <button
                  type="button"
                  onClick={() => setMintOpen(false)}
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleMintKey} className="p-5 space-y-4">
                <div>
                  <label
                    htmlFor="api-key-name"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                  >
                    Key Name
                  </label>
                  <input
                    id="api-key-name"
                    type="text"
                    required
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    placeholder="Fraud Detection Prod Cluster"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label
                    htmlFor="api-key-team"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                  >
                    Assigned Team
                  </label>
                  <select
                    id="api-key-team"
                    required
                    value={selectedTeam}
                    onChange={(e) => setSelectedTeam(e.target.value)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  >
                    {prodTeams.length === 0 ? (
                      <option value="">No organizational teams available</option>
                    ) : (
                      prodTeams.map((team) => (
                        <option key={team.team_id} value={team.team_id}>
                          {team.display_name} ({team.team_id})
                        </option>
                      ))
                    )}
                  </select>
                </div>

                {mintError && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {mintError}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                  <button
                    type="button"
                    onClick={() => setMintOpen(false)}
                    className="rounded-md border border-slate-300 dark:border-[#1D3868] px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={minting || prodTeams.length === 0}
                    className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50"
                  >
                    {minting ? 'Minting...' : 'Mint API Key'}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

