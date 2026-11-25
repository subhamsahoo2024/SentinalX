'use client';

import { useWebSocketStream, type WebSocketConnectionStatus } from '@/hooks/useWebSocketStream';
import { cn } from '@/lib/utils';

interface LiveConnectionBadgeProps {
  status?: WebSocketConnectionStatus;
}

function StreamConnectionBadge() {
  const { status } = useWebSocketStream('/ws/fleet');
  return <BadgeView status={status} />;
}

function BadgeView({ status }: { status: WebSocketConnectionStatus }) {
  const isConnected = status === 'connected';
  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium whitespace-nowrap shrink-0 tabular-nums',
        isConnected
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800/80 dark:bg-emerald-950/60 dark:text-emerald-300'
          : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800/80 dark:bg-amber-950/60 dark:text-amber-300',
      )}
      title={isConnected ? 'Telemetry stream connected' : 'Reconnecting to telemetry stream'}
    >
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          isConnected ? 'bg-emerald-600 dark:bg-emerald-400' : 'bg-amber-500 animate-pulse',
        )}
        aria-hidden="true"
      />
      <span>{isConnected ? 'LIVE' : 'RECONNECTING'}</span>
    </div>
  );
}

export function LiveConnectionBadge({ status }: LiveConnectionBadgeProps) {
  if (status !== undefined) {
    return <BadgeView status={status} />;
  }
  return <StreamConnectionBadge />;
}
