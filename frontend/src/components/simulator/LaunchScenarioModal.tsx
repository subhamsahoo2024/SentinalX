'use client';

import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  Clock,
  Coins,
  Flame,
  GitFork,
  Loader2,
  Lock,
  Play,
  RotateCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { launchSimulationScenario, ScenarioType } from '@/lib/api';

interface ScenarioOption {
  id: ScenarioType;
  title: string;
  badge: string;
  badgeStyle: string;
  icon: React.ComponentType<{ className?: string }>;
  iconStyle: string;
  description: string;
}

const SCENARIOS: ScenarioOption[] = [
  {
    id: 'normal',
    title: 'Normal IT Triage',
    badge: 'HEALTHY',
    badgeStyle: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    icon: ShieldCheck,
    iconStyle: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
    description:
      'Coordinator delegates to Diagnostic & Remediation agents with PII redaction and exact cost roll-up.',
  },
  {
    id: 'hitl',
    title: 'HITL Production Failover',
    badge: 'GOVERNANCE GATE',
    badgeStyle: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    icon: Lock,
    iconStyle: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    description:
      'Pauses execution at restart_production_cluster until an approver signs off.',
  },
  {
    id: 'loop',
    title: 'Infinite Tool Loop',
    badge: 'ANOMALY',
    badgeStyle: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    icon: RotateCw,
    iconStyle: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
    description:
      'Repeats query_flaky_endpoint 4 times with identical args, triggering LOOP_DETECTED.',
  },
  {
    id: 'slow_loop',
    title: 'Runaway Loop (Kill-Switch)',
    badge: 'ACTIVE CONTROL',
    badgeStyle: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    icon: Flame,
    iconStyle: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
    description:
      '15-step slow loop designed for testing live Kill Run abort or budget circuit-breaker.',
  },
  {
    id: 'cascade',
    title: 'Cascading Failure',
    badge: 'ROOT CAUSE',
    badgeStyle: 'bg-red-500/10 text-red-400 border-red-500/30',
    icon: GitFork,
    iconStyle: 'text-red-400 bg-red-500/10 border-red-500/30',
    description:
      'Upstream JSON schema corruption propagates downstream, highlighting the origin span.',
  },
  {
    id: 'budget',
    title: 'Token Budget Overrun',
    badge: 'COST GUARD',
    badgeStyle: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
    icon: Coins,
    iconStyle: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
    description:
      'Consumes ~7,500 tokens, exceeding policy limits and firing BUDGET_EXCEEDED.',
  },
  {
    id: 'stall',
    title: 'Stalled Worker Watchdog',
    badge: 'WATCHDOG',
    badgeStyle: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
    icon: Clock,
    iconStyle: 'text-sky-400 bg-sky-500/10 border-sky-500/30',
    description:
      'Drops heartbeats mid-run so the background watchdog marks the run STALLED.',
  },
];

const subscribeNoop = () => () => {};

export function LaunchScenarioModal() {
  const router = useRouter();
  const isMounted = useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false
  );
  const [isOpen, setIsOpen] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioType>('normal');
  const [team, setTeam] = useState<string>('it-ops');
  const [liveLlm, setLiveLlm] = useState<boolean>(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  // Lock body scroll when modal is active
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  const handleLaunch = async () => {
    setIsLaunching(true);
    setErrorMessage(null);

    try {
      const res = await launchSimulationScenario({
        scenario: selectedScenario,
        team,
        live_llm: liveLlm,
      });

      setIsOpen(false);
      router.push(`/runs/${res.run_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsLaunching(false);
    }
  };

  return (
    <>
      {/* Primary Trigger Button */}
      <button
        type="button"
        onClick={() => {
          setErrorMessage(null);
          setIsOpen(true);
        }}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold tracking-wide transition-all shadow-sm shadow-indigo-600/30 active:scale-95 shrink-0"
      >
        <Play className="w-3.5 h-3.5 fill-current" />
        <span>Launch Scenario</span>
      </button>

      {/* Modal Backdrop & Dialog (Rendered in Portal to escape parent header backdrop-blur stacking context) */}
      {isMounted && isOpen && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="simulator-modal-title"
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150 overflow-y-auto"
        >
          <div
            className="w-full max-w-3xl rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden flex flex-col max-h-[85vh] my-auto animate-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/50 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 text-indigo-400 flex items-center justify-center">
                  <Play className="w-4 h-4 fill-current ml-0.5" />
                </div>
                <div>
                  <h2
                    id="simulator-modal-title"
                    className="text-sm font-bold text-slate-100 tracking-tight"
                  >
                    Scenario & Chaos Simulator Launcher
                  </h2>
                  <p className="text-xs text-slate-400">
                    Select a multi-agent scenario to inject runtime anomalies, evaluate governance, or trace DAG lineage.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Error Alert (e.g. 403 Forbidden for Viewer role) */}
            {errorMessage && (
              <div className="mx-6 mt-4 p-3.5 rounded-xl bg-rose-950/60 border border-rose-500/50 text-rose-200 text-xs flex items-start gap-3">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="font-semibold text-rose-100">{errorMessage}</div>
                  {(errorMessage.toLowerCase().includes('viewer') ||
                    errorMessage.includes('403')) && (
                    <div className="text-[11px] text-rose-300/80 mt-1">
                      Read-only auditors cannot launch simulation workflows. Use the user session menu in the top right to switch to an Operator, Approver, or Admin account.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 2-Column Grid of 7 Scenarios */}
            <div className="p-6 overflow-y-auto min-h-0 flex-1 space-y-3">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Select Execution Profile
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {SCENARIOS.map((sc) => {
                  const isSelected = selectedScenario === sc.id;
                  const Icon = sc.icon;

                  return (
                    <div
                      key={sc.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedScenario(sc.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          setSelectedScenario(sc.id);
                        }
                      }}
                      className={`p-3.5 rounded-xl border text-left cursor-pointer transition-all select-none ${
                        isSelected
                          ? 'border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50 shadow-md shadow-indigo-950/50'
                          : 'border-slate-800/80 bg-slate-950/40 hover:bg-slate-800/50 hover:border-slate-700/80'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <div
                            className={`w-6 h-6 rounded-md flex items-center justify-center border text-xs shrink-0 ${sc.iconStyle}`}
                          >
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className="text-xs font-bold text-slate-100">
                            {sc.title}
                          </span>
                        </div>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border shrink-0 ${sc.badgeStyle}`}
                        >
                          {sc.badge}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed pl-8">
                        {sc.description}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Controls Bar at the Bottom */}
            <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/70 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 shrink-0">
              <div className="flex flex-wrap items-center gap-4">
                {/* Team Selector */}
                <div className="flex items-center gap-2">
                  <label
                    htmlFor="simulator-team"
                    className="text-xs font-semibold text-slate-300"
                  >
                    Team:
                  </label>
                  <select
                    id="simulator-team"
                    value={team}
                    onChange={(e) => setTeam(e.target.value)}
                    className="bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="it-ops">it-ops</option>
                    <option value="finance-ai">finance-ai</option>
                    <option value="sec-ops">sec-ops</option>
                  </select>
                </div>

                {/* Live LLM Checkbox */}
                <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-300">
                  <input
                    type="checkbox"
                    checked={liveLlm}
                    onChange={(e) => setLiveLlm(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                  />
                  <span>Use Live LLM Provider</span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    (Mock by default)
                  </span>
                </label>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  disabled={isLaunching}
                  className="px-3 py-1.5 rounded-lg border border-slate-700 text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleLaunch}
                  disabled={isLaunching}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold tracking-wide transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-indigo-600/30"
                >
                  {isLaunching ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 fill-current" />
                  )}
                  <span>{isLaunching ? 'Launching...' : 'Launch Workflow'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

