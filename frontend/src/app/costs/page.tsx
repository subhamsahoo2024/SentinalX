'use client';

import { Coins } from 'lucide-react';

export default function CostsPage() {
  return (
    <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-100">
          Cost & Token Attribution
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Detailed cost breakdowns and token consumption attributed by team, agent, and model version.
        </p>
      </div>

      <div className="p-12 rounded-xl bg-slate-900/40 border border-slate-800 text-center space-y-3">
        <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center mx-auto">
          <Coins className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-200">
          Attribution Engine Ready
        </h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          Cost tables and token breakdowns will aggregate dynamically from incoming telemetry spans.
        </p>
      </div>
    </div>
  );
}
