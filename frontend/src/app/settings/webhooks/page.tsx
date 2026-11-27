'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertCircle,
  BellRing,
  Check,
  CheckCircle2,
  Copy,
  Eye,
  EyeOff,
  Info,
  Plus,
  Send,
  Shield,
  Trash2,
  Webhook,
  X,
  XCircle,
} from 'lucide-react';
import { useIsClient } from '@/hooks/use-is-client';
import {
  createWebhook,
  deleteWebhook,
  fetchTeams,
  fetchWebhooks,
  testWebhook,
  updateWebhook,
} from '@/lib/api';
import { getAuthUserSnapshot, subscribeAuth } from '@/lib/auth';
import { formatRelativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  TeamDTO,
  WebhookEndpointDTO,
  WebhookEventType,
  WebhookTestResultDTO,
} from '@/types/telemetry';

const ALL_WEBHOOK_EVENTS: {
  value: WebhookEventType;
  label: string;
  description: string;
}[] = [
  {
    value: 'APPROVAL_REQUIRED',
    label: 'APPROVAL_REQUIRED',
    description: 'Human-in-the-loop gate awaiting decision',
  },
  {
    value: 'CASCADE_FAILURE',
    label: 'CASCADE_FAILURE',
    description: 'Root-cause failure impacting downstream spans',
  },
  {
    value: 'LOOP_DETECTED',
    label: 'LOOP_DETECTED',
    description: 'Repeated tool invocation loop exceeded threshold',
  },
  {
    value: 'BUDGET_EXCEEDED',
    label: 'BUDGET_EXCEEDED',
    description: 'Run token or USD spend budget overrun',
  },
  {
    value: 'RUN_STALLED',
    label: 'RUN_STALLED',
    description: 'Watchdog detected stalled in-flight run',
  },
];

function maskSecret(secret: string): string {
  if (secret.length <= 12) {
    return 'whsec_••••••••••••';
  }
  return `${secret.slice(0, 10)}${'•'.repeat(16)}${secret.slice(-4)}`;
}

export default function WebhooksPage() {
  const mounted = useIsClient();
  const currentUser = useSyncExternalStore(
    subscribeAuth,
    getAuthUserSnapshot,
    () => null,
  );
  const isOrgAdmin =
    currentUser?.role === 'admin' && currentUser?.is_demo !== true;

  const [webhooks, setWebhooks] = useState<WebhookEndpointDTO[]>([]);
  const [teams, setTeams] = useState<TeamDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Create modal state
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<string>('');
  const [selectedEvents, setSelectedEvents] = useState<WebhookEventType[]>(
    ALL_WEBHOOK_EVENTS.map((e) => e.value),
  );
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Per-card interactive state
  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, WebhookTestResultDTO>
  >({});
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const prodTeams = teams.filter((team) => team.team_id !== 'demo-sandbox');

  const loadData = useCallback(async () => {
    if (!isOrgAdmin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [webhooksData, teamsData] = await Promise.all([
        fetchWebhooks(),
        fetchTeams(),
      ]);
      setWebhooks(webhooksData);
      setTeams(teamsData);
      setPageError(null);
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to load webhooks',
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

  const openCreateModal = () => {
    setCreateError(null);
    setName('');
    setUrl('');
    setSelectedTeam('');
    setSelectedEvents(ALL_WEBHOOK_EVENTS.map((e) => e.value));
    setCreateOpen(true);
  };

  const toggleEventType = (eventType: WebhookEventType) => {
    setSelectedEvents((prev) =>
      prev.includes(eventType)
        ? prev.filter((item) => item !== eventType)
        : [...prev, eventType],
    );
  };

  const handleCreateWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creating) return;

    if (!name.trim() || !url.trim()) {
      setCreateError('Provide both a webhook name and target URL.');
      return;
    }
    if (selectedEvents.length === 0) {
      setCreateError('Select at least one subscribed incident event type.');
      return;
    }

    setCreating(true);
    setCreateError(null);
    try {
      const created = await createWebhook({
        name: name.trim(),
        team: selectedTeam === '' ? null : selectedTeam,
        url: url.trim(),
        event_types: selectedEvents,
      });
      setWebhooks((prev) => [created, ...prev]);
      setCreateOpen(false);
    } catch (err: unknown) {
      setCreateError(
        err instanceof Error ? err.message : 'Failed to create webhook',
      );
    } finally {
      setCreating(false);
    }
  };

  const handleToggleEnabled = async (endpoint: WebhookEndpointDTO) => {
    if (togglingId === endpoint.webhook_id) return;
    setTogglingId(endpoint.webhook_id);
    setPageError(null);
    try {
      const updated = await updateWebhook(endpoint.webhook_id, {
        enabled: !endpoint.enabled,
      });
      setWebhooks((prev) =>
        prev.map((item) =>
          item.webhook_id === endpoint.webhook_id ? updated : item,
        ),
      );
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to update webhook state',
      );
    } finally {
      setTogglingId(null);
    }
  };

  const handleSendTestPing = async (webhookId: string) => {
    if (testingId === webhookId) return;
    setTestingId(webhookId);
    setPageError(null);
    try {
      const result = await testWebhook(webhookId);
      setTestResults((prev) => ({ ...prev, [webhookId]: result }));
      const nowIso = new Date().toISOString();
      setWebhooks((prev) =>
        prev.map((ep) =>
          ep.webhook_id === webhookId
            ? {
                ...ep,
                last_status_code: result.status_code,
                last_triggered_at: nowIso,
              }
            : ep,
        ),
      );
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to deliver test ping',
      );
    } finally {
      setTestingId(null);
    }
  };

  const handleDeleteWebhook = async (webhookId: string) => {
    if (deletingId === webhookId) return;
    setDeletingId(webhookId);
    setPageError(null);
    try {
      await deleteWebhook(webhookId);
      setWebhooks((prev) => prev.filter((ep) => ep.webhook_id !== webhookId));
    } catch (err: unknown) {
      setPageError(
        err instanceof Error ? err.message : 'Failed to delete webhook',
      );
    } finally {
      setDeletingId(null);
    }
  };

  const handleCopySecret = async (webhookId: string, secret: string) => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopiedId(webhookId);
      setTimeout(() => {
        setCopiedId((current) => (current === webhookId ? null : current));
      }, 2000);
    } catch {
      setPageError('Clipboard access failed. Reveal and copy the secret manually.');
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
              Only non-demo organization administrators can configure outbound incident webhooks.
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

      {/* Header Action Card */}
      <section className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-sm px-5 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Webhook
            className="h-4 w-4 text-[#0257D5] dark:text-[#00C2FF]"
            aria-hidden="true"
          />
          <div>
            <h2 className="text-sm font-semibold text-[#041533] dark:text-slate-100">
              Outbound Incident Webhooks
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Deliver HMAC-SHA256 signed incident notifications to Slack, PagerDuty, or SIEM receivers in real time.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3.5 py-2 text-xs font-medium text-white hover:bg-[#0346B0] transition-colors whitespace-nowrap"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Add Webhook Endpoint</span>
        </button>
      </section>

      {/* Configured Webhooks List */}
      {loading ? (
        <div className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] p-8 text-center text-xs text-slate-500 dark:text-slate-400">
          Loading configured webhook endpoints...
        </div>
      ) : webhooks.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] p-10 text-center space-y-2">
          <BellRing
            className="h-6 w-6 mx-auto text-[#0257D5] dark:text-[#00C2FF]"
            aria-hidden="true"
          />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            No Outbound Webhooks Configured
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
            Register an endpoint to receive signed HTTP POST notifications when approvals gate execution or anomalies trigger alerts.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {webhooks.map((endpoint) => {
            const isRevealed = Boolean(revealedSecrets[endpoint.webhook_id]);
            const isCopied = copiedId === endpoint.webhook_id;
            const testResult = testResults[endpoint.webhook_id];
            const statusCode = endpoint.last_status_code;
            const isHealthyStatus =
              statusCode !== null && statusCode >= 200 && statusCode < 300;

            return (
              <article
                key={endpoint.webhook_id}
                className="rounded-xl border border-[#D4E2F4] dark:border-[#172E56] bg-white dark:bg-[#07152E] shadow-sm p-5 space-y-4"
              >
                {/* Top row: Name, Scope Badge, Last Status, Enabled Switch */}
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-[#041533] dark:text-slate-100">
                        {endpoint.name}
                      </h3>
                      <span
                        className={cn(
                          'inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-mono',
                          endpoint.team === null
                            ? 'border-indigo-300 dark:border-indigo-500/40 bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300'
                            : 'border-[#93C5FD] dark:border-[#00C2FF]/40 bg-[#EFF6FF] dark:bg-[#0257D5]/25 text-[#0257D5] dark:text-[#7DD3FC]',
                        )}
                      >
                        {endpoint.team === null
                          ? 'Org-Wide'
                          : `Team: ${endpoint.team}`}
                      </span>

                      {statusCode !== null && (
                        <span
                          className={cn(
                            'inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-mono font-medium',
                            isHealthyStatus
                              ? 'border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                              : 'border-rose-300 dark:border-rose-500/40 bg-rose-50 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300',
                          )}
                        >
                          {isHealthyStatus ? (
                            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          ) : (
                            <XCircle className="h-3 w-3" aria-hidden="true" />
                          )}
                          <span>
                            {statusCode === 200 ? '200 OK' : `HTTP ${statusCode}`}
                          </span>
                        </span>
                      )}
                    </div>

                    <p className="font-mono text-xs text-slate-700 dark:text-slate-300 break-all">
                      {endpoint.url}
                    </p>
                  </div>

                  {/* Enabled Switch */}
                  <div className="flex items-center gap-2.5 shrink-0">
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
                      {endpoint.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={endpoint.enabled}
                      aria-label={`Toggle ${endpoint.name}`}
                      disabled={togglingId === endpoint.webhook_id}
                      onClick={() => void handleToggleEnabled(endpoint)}
                      className={cn(
                        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border transition-colors disabled:opacity-50',
                        endpoint.enabled
                          ? 'border-[#0257D5] bg-[#0257D5] dark:border-[#00C2FF] dark:bg-[#0257D5]'
                          : 'border-slate-300 dark:border-[#1D3868] bg-slate-200 dark:bg-[#0A1B3B]',
                      )}
                    >
                      <span
                        className={cn(
                          'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
                          endpoint.enabled ? 'translate-x-4' : 'translate-x-0.5',
                        )}
                      />
                    </button>
                  </div>
                </div>

                {/* Subscribed Event Types Pills */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mr-1">
                    Events:
                  </span>
                  {endpoint.event_types.map((evt) => (
                    <span
                      key={evt}
                      className="inline-flex rounded border border-slate-200 dark:border-[#1D3868] bg-slate-50 dark:bg-[#0A1B3B] px-2 py-0.5 text-[11px] font-mono text-slate-700 dark:text-slate-300"
                    >
                      {evt}
                    </span>
                  ))}
                </div>

                {/* Signing Secret & Actions Footer */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-200 dark:border-[#172E56]">
                  <div className="flex flex-wrap items-center gap-2 min-w-0">
                    <span
                      title="Verify incoming requests using HMAC-SHA256 header: X-Sentinel-Signature: t=<ts>,v1=<hmac_sha256>"
                      className="inline-flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400 cursor-help"
                    >
                      <Info className="h-3.5 w-3.5 text-[#0257D5] dark:text-[#00C2FF]" aria-hidden="true" />
                      <span>Signing Secret</span>
                    </span>

                    <code className="rounded border border-slate-200 dark:border-[#1D3868] bg-slate-50 dark:bg-[#030A17] px-2.5 py-1 text-[11px] font-mono text-slate-800 dark:text-slate-200">
                      {isRevealed
                        ? endpoint.signing_secret
                        : maskSecret(endpoint.signing_secret)}
                    </code>

                    <button
                      type="button"
                      onClick={() =>
                        setRevealedSecrets((prev) => ({
                          ...prev,
                          [endpoint.webhook_id]: !prev[endpoint.webhook_id],
                        }))
                      }
                      title={isRevealed ? 'Hide secret' : 'Reveal secret'}
                      aria-label={isRevealed ? 'Hide signing secret' : 'Reveal signing secret'}
                      className="inline-flex items-center gap-1 rounded border border-slate-200 dark:border-[#1D3868] px-2 py-1 text-[11px] text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-[#0A1B3B] transition-colors"
                    >
                      {isRevealed ? (
                        <EyeOff className="h-3 w-3" aria-hidden="true" />
                      ) : (
                        <Eye className="h-3 w-3" aria-hidden="true" />
                      )}
                      <span>{isRevealed ? 'Hide' : 'Reveal'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        void handleCopySecret(
                          endpoint.webhook_id,
                          endpoint.signing_secret,
                        )
                      }
                      title="Header format: X-Sentinel-Signature: t=<ts>,v1=<hmac_sha256>"
                      className="inline-flex items-center gap-1 rounded border border-slate-200 dark:border-[#1D3868] px-2 py-1 text-[11px] text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-[#0A1B3B] transition-colors"
                    >
                      {isCopied ? (
                        <>
                          <Check className="h-3 w-3 text-emerald-500" aria-hidden="true" />
                          <span>Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3" aria-hidden="true" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>

                    <span className="hidden xl:inline text-[11px] font-mono text-slate-400 dark:text-slate-500">
                      X-Sentinel-Signature: t=&lt;ts&gt;,v1=&lt;hmac_sha256&gt;
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    {endpoint.last_triggered_at && (
                      <span className="text-[11px] text-slate-500 dark:text-slate-400 mr-1">
                        Triggered {formatRelativeTime(endpoint.last_triggered_at)}
                      </span>
                    )}

                    {testResult && (
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-medium',
                          testResult.delivered
                            ? 'border-emerald-300 dark:border-emerald-500/40 bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                            : 'border-rose-300 dark:border-rose-500/40 bg-rose-50 dark:bg-rose-500/15 text-rose-700 dark:text-rose-300',
                        )}
                      >
                        {testResult.delivered
                          ? `Ping Delivered (${testResult.status_code})`
                          : `Ping Failed (${testResult.status_code ?? 'Network Error'})`}
                      </span>
                    )}

                    <button
                      type="button"
                      disabled={testingId === endpoint.webhook_id}
                      onClick={() => void handleSendTestPing(endpoint.webhook_id)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-[#93C5FD] dark:border-[#00C2FF]/40 bg-[#EFF6FF] dark:bg-[#0A1B3B] px-2.5 py-1 text-[11px] font-medium text-[#0257D5] dark:text-[#7DD3FC] hover:bg-[#DBEAFE] dark:hover:bg-[#102650] disabled:opacity-50 transition-colors"
                    >
                      <Send className="h-3 w-3" aria-hidden="true" />
                      <span>
                        {testingId === endpoint.webhook_id
                          ? 'Sending...'
                          : 'Send Test Ping'}
                      </span>
                    </button>

                    <button
                      type="button"
                      disabled={deletingId === endpoint.webhook_id}
                      onClick={() => void handleDeleteWebhook(endpoint.webhook_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-red-200 dark:border-red-800/60 px-2.5 py-1 text-[11px] font-medium text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/50 disabled:opacity-50 transition-colors"
                    >
                      <Trash2 className="h-3 w-3" aria-hidden="true" />
                      <span>
                        {deletingId === endpoint.webhook_id
                          ? 'Deleting...'
                          : 'Delete'}
                      </span>
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Create Webhook Modal */}
      {mounted &&
        createOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setCreateOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-webhook-title"
              className="w-full max-w-lg rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <h3
                  id="create-webhook-title"
                  className="text-base font-semibold text-slate-900 dark:text-slate-100"
                >
                  Add Outbound Webhook Endpoint
                </h3>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={handleCreateWebhook} className="p-5 space-y-4">
                <div>
                  <label
                    htmlFor="webhook-name"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                  >
                    Endpoint Name
                  </label>
                  <input
                    id="webhook-name"
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Fraud On-Call PagerDuty"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label
                    htmlFor="webhook-url"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                  >
                    Target URL
                  </label>
                  <input
                    id="webhook-url"
                    type="url"
                    required
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://events.pagerduty.com/v2/enqueue"
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs font-mono text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  />
                </div>

                <div>
                  <label
                    htmlFor="webhook-team"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                  >
                    Team Scope
                  </label>
                  <select
                    id="webhook-team"
                    value={selectedTeam}
                    onChange={(e) => setSelectedTeam(e.target.value)}
                    className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                  >
                    <option value="">All Organizational Teams</option>
                    {prodTeams.map((team) => (
                      <option key={team.team_id} value={team.team_id}>
                        {team.display_name} ({team.team_id})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <span className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-2">
                    Subscribed Incident Events
                  </span>
                  <div className="space-y-2 rounded-md border border-slate-200 dark:border-[#172E56] bg-slate-50/60 dark:bg-[#040B18] p-3">
                    {ALL_WEBHOOK_EVENTS.map((evt) => {
                      const checked = selectedEvents.includes(evt.value);
                      return (
                        <label
                          key={evt.value}
                          className="flex items-start gap-2.5 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleEventType(evt.value)}
                            className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 dark:border-[#1D3868] text-[#0257D5] focus:ring-[#0257D5]"
                          />
                          <div className="min-w-0">
                            <span className="block text-xs font-mono font-medium text-slate-900 dark:text-slate-100">
                              {evt.label}
                            </span>
                            <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                              {evt.description}
                            </span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>

                {createError && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {createError}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                  <button
                    type="button"
                    onClick={() => setCreateOpen(false)}
                    className="rounded-md border border-slate-300 dark:border-[#1D3868] px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650]"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50"
                  >
                    {creating ? 'Saving...' : 'Create Webhook'}
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

