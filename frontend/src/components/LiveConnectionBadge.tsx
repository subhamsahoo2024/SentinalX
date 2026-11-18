'use client';

import { useWebSocketStream } from '@/hooks/useWebSocketStream';
import { Radio } from 'lucide-react';

export function LiveConnectionBadge() {
  const { status } = useWebSocketStream('/ws/fleet');

  const isConnected = status === 'connected';

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono font-medium border transition-colors ${
        isConnected
          ? 'bg-emerald-950/50 border-emerald-500/30 text-emerald-400'
          : 'bg-amber-950/50 border-amber-500/30 text-amber-400'
      }`}
      title={isConnected ? 'Connected to SentinelX PubSub' : 'Reconnecting to SentinelX PubSub'}
    >
      <span className="relative flex h-2 w-2">
        <span
          className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
            isConnected ? 'bg-emerald-400' : 'bg-amber-400'
          }`}
        />
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            isConnected ? 'bg-emerald-500' : 'bg-amber-500'
          }`}
        />
      </span>
      <Radio className="w-3.5 h-3.5" />
      <span>{isConnected ? 'LIVE' : 'RECONNECTING'}</span>
    </div>
  );
}

