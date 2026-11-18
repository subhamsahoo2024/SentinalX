'use client';

import { usePathname } from 'next/navigation';
import { LiveConnectionBadge } from './LiveConnectionBadge';

export function Header() {
  const pathname = usePathname();

  const getPageTitle = (path: string) => {
    if (path === '/') return 'Fleet Overview';
    if (path.startsWith('/approvals')) return 'Human-in-the-Loop Approvals';
    if (path.startsWith('/costs')) return 'Cost & Token Attribution';
    if (path.startsWith('/runs/')) return 'Run Execution Detail';
    return 'Observability Tower';
  };

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/40 backdrop-blur-md px-6 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-base font-semibold text-slate-100 tracking-tight">
          {getPageTitle(pathname)}
        </h1>
        <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/80 text-slate-400 border border-slate-700/60">
          Telemetry Bus v1.0
        </span>
      </div>

      <div className="flex items-center gap-4">
        {/* Live WebSocket connection indicator */}
        <LiveConnectionBadge />
      </div>
    </header>
  );
}
