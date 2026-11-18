'use client';

import { Clock } from 'lucide-react';

export default function ApprovalsPage() {
  return (
    <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-100">
          Human-in-the-Loop Approvals
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Review, approve, or reject high-impact agent actions requiring human authorization.
        </p>
      </div>

      <div className="p-12 rounded-xl bg-slate-900/40 border border-slate-800 text-center space-y-3">
        <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mx-auto">
          <Clock className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-200">
          No Pending Approvals
        </h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          When an agent triggers an action configured with human approval policies, the execution pauses and awaits decision here.
        </p>
      </div>
    </div>
  );
}
