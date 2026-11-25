'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { AlertCircle, Play, X } from 'lucide-react';
import { useIsClient } from '@/hooks/use-is-client';
import { launchSimulationScenario, type ScenarioType } from '@/lib/api';
import { cn } from '@/lib/utils';

interface ScenarioOption {
  id: ScenarioType;
  title: string;
  description: string;
}

const SCENARIOS: ScenarioOption[] = [
  {
    id: 'normal',
    title: 'Normal IT Triage',
    description: 'Healthy delegation, PII redaction, and subtree cost roll-up.',
  },
  {
    id: 'hitl',
    title: 'HITL Production Failover',
    description: 'Pre-execution gate pausing at restart_production_cluster.',
  },
  {
    id: 'loop',
    title: 'Infinite Tool Loop',
    description: '4 repetitive tool invocations triggering LOOP_DETECTED.',
  },
  {
    id: 'slow_loop',
    title: 'Runaway Loop',
    description: '15-step slow loop designed for testing live kill-switch abort.',
  },
  {
    id: 'cascade',
    title: 'Cascading Failure',
    description: 'Schema corruption propagating downstream across agents.',
  },
  {
    id: 'budget',
    title: 'Token Budget Overrun',
    description: 'Exceeds token ceiling firing BUDGET_EXCEEDED circuit breaker.',
  },
  {
    id: 'stall',
    title: 'Stalled Worker Watchdog',
    description: 'Heartbeat drop triggering watchdog STALLED status.',
  },
];

export function LaunchScenarioModal() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [selected, setSelected] = useState<ScenarioType>('normal');
  const [team, setTeam] = useState('it-ops');
  const [useLiveLlm, setUseLiveLlm] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const mounted = useIsClient();

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  const handleLaunch = async () => {
    if (launching) return;
    setLaunching(true);
    setErrorMessage(null);
    try {
      const res = await launchSimulationScenario({
        scenario: selected,
        team,
        live_llm: useLiveLlm,
      });
      setIsOpen(false);
      router.push(`/runs/${encodeURIComponent(res.run_id)}`);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setErrorMessage(null);
          setIsOpen(true);
        }}
        className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#0346B0] transition-colors whitespace-nowrap shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00A8E8]"
      >
        <Play className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Launch Simulation</span>
      </button>

      {mounted &&
        isOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 dark:bg-black/75 p-4"
            onClick={() => setIsOpen(false)}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="launch-sim-title"
              className="w-full max-w-xl rounded-lg border border-[#D4E2F4] dark:border-[#1D3868] bg-white dark:bg-[#07152E] shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#172E56] px-5 py-4">
                <div>
                  <h2
                    id="launch-sim-title"
                    className="text-base font-semibold text-slate-900 dark:text-slate-100"
                  >
                    Launch Telemetry Scenario
                  </h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Spawn a multi-agent execution trace to test governance gates and lineage.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="rounded-md p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#0D2247]"
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {errorMessage && (
                <div className="mx-5 mt-4 rounded-md border border-red-200 dark:border-red-800/80 bg-red-50 dark:bg-red-950/60 p-3 text-xs text-red-700 dark:text-red-300 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="flex-1">
                    <p className="font-semibold">{errorMessage}</p>
                    {(errorMessage.toLowerCase().includes('viewer') ||
                      errorMessage.includes('403')) && (
                      <p className="mt-1 text-[11px] opacity-90">
                        Viewers cannot launch simulation scenarios. Switch to an Operator, Approver, or Admin role in the top right session menu.
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {SCENARIOS.map((sc) => {
                    const active = selected === sc.id;
                    return (
                      <button
                        key={sc.id}
                        type="button"
                        onClick={() => setSelected(sc.id)}
                        className={cn(
                          'rounded-md border p-3 text-left transition-colors',
                          active
                            ? 'border-[#0257D5] bg-[#EFF6FF] dark:border-[#00C2FF] dark:bg-[#0257D5]/25'
                            : 'border-[#D4E2F4] bg-white hover:bg-[#F5F9FF] dark:border-[#172E56] dark:bg-[#0A1B3B] dark:hover:bg-[#102650]',
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                            {sc.title}
                          </span>
                          <span className="text-[11px] font-mono text-slate-500 dark:text-[#7DD3FC]">
                            {sc.id}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400 leading-snug">
                          {sc.description}
                        </p>
                      </button>
                    );
                  })}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-200 dark:border-[#172E56]">
                  <div>
                    <label
                      htmlFor="sim-team-select"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1"
                    >
                      Target Team Scope
                    </label>
                    <select
                      id="sim-team-select"
                      value={team}
                      onChange={(e) => setTeam(e.target.value)}
                      className="w-full rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-[#0257D5] dark:focus:border-[#00C2FF] focus:outline-none"
                    >
                      <option value="it-ops">it-ops</option>
                      <option value="finance-ai">finance-ai</option>
                      <option value="sec-ops">sec-ops</option>
                    </select>
                  </div>

                  <div className="flex items-end pb-2">
                    <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={useLiveLlm}
                        onChange={(e) => setUseLiveLlm(e.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 text-[#0257D5] focus:ring-[#0257D5]"
                      />
                      <span>Enable Live LLM Mode</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 border-t border-slate-200 dark:border-[#172E56] px-5 py-3.5 bg-slate-50 dark:bg-[#040B18] rounded-b-lg">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="rounded-md border border-slate-300 dark:border-[#1D3868] bg-white dark:bg-[#0A1B3B] px-4 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#102650] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={launching}
                  onClick={() => void handleLaunch()}
                  className="rounded-md bg-[#0257D5] px-4 py-2 text-xs font-medium text-white hover:bg-[#0346B0] disabled:opacity-50 transition-colors"
                >
                  {launching ? 'Launching...' : 'Start Simulation'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
