import { formatDistanceToNowStrict } from 'date-fns';

export function formatUsd(amount: number | null | undefined, digits = 4): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) {
    return '—';
  }
  if (amount > 0 && amount < 0.0001) {
    return '<$0.0001';
  }
  return `$${Number(amount).toFixed(digits)}`;
}

export function formatTokens(count: number | null | undefined): string {
  if (count === null || count === undefined || Number.isNaN(count)) {
    return '—';
  }
  return new Intl.NumberFormat('en-US').format(count);
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) {
    return '—';
  }
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  if (ms < 60_000) {
    return `${(ms / 1000).toFixed(2)} s`;
  }
  const mins = Math.floor(ms / 60_000);
  const secs = ((ms % 60_000) / 1000).toFixed(1);
  return `${mins}m ${secs}s`;
}

export function computeRunDurationMs(
  startedAt: string,
  endedAt?: string | null,
): number | null {
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return null;
  if (!endedAt) return null;
  const end = Date.parse(endedAt);
  if (Number.isNaN(end)) return null;
  return Math.max(0, end - start);
}

export function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';
  return formatDistanceToNowStrict(date, { addSuffix: true });
}

export function formatUtcTimestamp(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

