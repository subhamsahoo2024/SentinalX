import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  Clock,
  PauseCircle,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatusBadgeProps {
  status: string;
  compact?: boolean;
  className?: string;
}

export function StatusBadge({ status, compact = false, className }: StatusBadgeProps) {
  const normalized = (status || '').toUpperCase();

  let tone =
    'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800/80 dark:text-slate-300 dark:border-slate-700';
  let Icon = Clock;

  if (normalized === 'SUCCEEDED' || normalized === 'APPROVED' || normalized === 'ACTIVE') {
    tone =
      'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800/80';
    Icon = CheckCircle2;
  } else if (normalized === 'RUNNING' || normalized === 'QUEUED') {
    tone =
      'bg-sky-50 text-sky-800 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800/80';
    Icon = Activity;
  } else if (
    normalized === 'AWAITING_APPROVAL' ||
    normalized === 'PENDING' ||
    normalized === 'IDLE' ||
    normalized === 'HIGH' ||
    normalized === 'MEDIUM'
  ) {
    tone =
      'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800/80';
    Icon = normalized === 'AWAITING_APPROVAL' || normalized === 'PENDING' ? ShieldAlert : Clock;
  } else if (
    normalized === 'FAILED' ||
    normalized === 'REJECTED' ||
    normalized === 'TIMED_OUT' ||
    normalized === 'CRITICAL'
  ) {
    tone =
      'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800/80';
    Icon = normalized === 'CRITICAL' ? AlertTriangle : XCircle;
  } else if (normalized === 'STALLED') {
    tone =
      'bg-violet-50 text-violet-800 border-violet-200 dark:bg-violet-950/60 dark:text-violet-300 dark:border-violet-800/80';
    Icon = PauseCircle;
  } else if (normalized === 'CANCELLED' || normalized === 'OFFLINE') {
    tone =
      'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800/70 dark:text-slate-400 dark:border-slate-700';
    Icon = Ban;
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border font-medium whitespace-nowrap shrink-0 tabular-nums',
        compact ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-0.5 text-xs',
        tone,
        className,
      )}
    >
      <Icon className={cn('shrink-0', compact ? 'h-3 w-3' : 'h-3.5 w-3.5')} aria-hidden="true" />
      <span>{normalized}</span>
    </span>
  );
}

