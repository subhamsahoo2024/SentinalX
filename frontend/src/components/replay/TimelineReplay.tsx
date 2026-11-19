'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  X,
  Bot,
  Cpu,
  Wrench,
  ShieldAlert,
  Clock,
  Coins,
  AlertCircle,
  Activity,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { LineageEdgeDTO, LineageNodeDTO } from '@/types/telemetry';

interface TimelineReplayProps {
  allNodes: LineageNodeDTO[];
  allEdges: LineageEdgeDTO[];
  onReplayFrame: (
    nodes: LineageNodeDTO[],
    edges: LineageEdgeDTO[],
    activeNode: LineageNodeDTO | null
  ) => void;
  onExitReplay: () => void;
}

export function TimelineReplay({
  allNodes,
  allEdges,
  onReplayFrame,
  onExitReplay,
}: TimelineReplayProps) {
  // 1. Sort all nodes chronologically by started_at ascending
  const sortedNodes = useMemo(() => {
    return [...allNodes].sort((a, b) => {
      const ta = new Date(a.started_at).getTime();
      const tb = new Date(b.started_at).getTime();
      if (ta !== tb) return ta - tb;
      return (a.attempt_number || 1) - (b.attempt_number || 1);
    });
  }, [allNodes]);

  const totalSteps = sortedNodes.length;
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const activeEventRef = useRef<HTMLDivElement | null>(null);

  // Initial reference timestamp (t0)
  const startTimeMs = useMemo(() => {
    if (sortedNodes.length === 0) return 0;
    return new Date(sortedNodes[0].started_at).getTime();
  }, [sortedNodes]);

  // Compute and emit frame whenever currentStep or sortedNodes change
  useEffect(() => {
    if (totalSteps === 0) {
      onReplayFrame([], [], null);
      return;
    }

    const clampedStep = Math.min(Math.max(1, currentStep), totalSteps);
    const activeNode = sortedNodes[clampedStep - 1];
    const currentTimestamp = new Date(activeNode.started_at).getTime();

    // Nodes visible up to step k
    const visibleRawNodes = sortedNodes.slice(0, clampedStep);

    // Compute historical status: if ended_at is null or ended_at > currentTimestamp, it was RUNNING
    const reconstructedNodes: LineageNodeDTO[] = visibleRawNodes.map((node) => {
      const endedMs = node.ended_at ? new Date(node.ended_at).getTime() : null;
      let historicalStatus = node.status;
      if (endedMs === null || endedMs > currentTimestamp) {
        historicalStatus = 'RUNNING';
      }
      return {
        ...node,
        status: historicalStatus,
      };
    });

    const visibleNodeIds = new Set(reconstructedNodes.map((n) => n.id));
    const visibleEdges = allEdges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    onReplayFrame(reconstructedNodes, visibleEdges, activeNode);
  }, [currentStep, sortedNodes, totalSteps, allEdges, onReplayFrame]);

  // Auto-play timer: advances 1 step every 800ms
  useEffect(() => {
    if (!isPlaying) return;

    if (currentStep >= totalSteps) {
      const timeoutId = setTimeout(() => setIsPlaying(false), 0);
      return () => clearTimeout(timeoutId);
    }

    const timer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev >= totalSteps) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 800);

    return () => clearInterval(timer);
  }, [isPlaying, currentStep, totalSteps]);

  // Scroll active event in feed into view
  useEffect(() => {
    if (activeEventRef.current) {
      activeEventRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [currentStep]);

  // Handle Play/Pause toggle
  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
    } else {
      if (currentStep >= totalSteps) {
        setCurrentStep(1);
      }
      setIsPlaying(true);
    }
  };

  const handleStepBack = () => {
    setIsPlaying(false);
    setCurrentStep((prev) => Math.max(1, prev - 1));
  };

  const handleStepForward = () => {
    setIsPlaying(false);
    setCurrentStep((prev) => Math.min(totalSteps, prev + 1));
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStep(1);
  };

  if (totalSteps === 0) {
    return (
      <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-slate-400 font-mono text-xs flex items-center justify-between">
        <span>No chronological spans available to replay.</span>
        <button
          onClick={onExitReplay}
          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const activeNode = sortedNodes[currentStep - 1];
  const activeOffsetSec = (
    (new Date(activeNode.started_at).getTime() - startTimeMs) /
    1000
  ).toFixed(2);

  return (
    <div className="w-full rounded-xl bg-slate-900/95 border border-cyan-500/30 shadow-2xl backdrop-blur-md overflow-hidden flex flex-col z-20">
      {/* Top Header & Replay Controls */}
      <div className="p-3.5 sm:p-4 border-b border-slate-800 bg-slate-950/60 flex flex-col gap-3">
        {/* Title row */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-cyan-950/80 border border-cyan-500/50 flex items-center justify-center text-cyan-400 shrink-0">
              <Activity className="w-4 h-4 animate-pulse" />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-slate-100 flex items-center gap-2">
                <span>Chronological Execution Replay</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                  Step {currentStep} of {totalSteps}
                </span>
                <span className="text-[11px] font-mono text-cyan-400 font-semibold">
                  +{activeOffsetSec}s
                </span>
              </div>
            </div>
          </div>

          {/* Exit Replay Button */}
          <button
            onClick={onExitReplay}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors"
            title="Exit Replay"
          >
            <X className="w-3.5 h-3.5" />
            <span>Exit Replay</span>
          </button>
        </div>

        {/* Transport Controls & Scrubber */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Button Group */}
          <div className="flex items-center gap-1.5 shrink-0 self-center sm:self-auto">
            <button
              onClick={handleReset}
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 text-slate-300 transition-colors"
              title="Reset to Step 1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleStepBack}
              disabled={currentStep <= 1}
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 text-slate-300 transition-colors disabled:opacity-40 disabled:pointer-events-none"
              title="Step Back"
            >
              <SkipBack className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={togglePlay}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition-colors shadow-sm',
                isPlaying
                  ? 'bg-amber-500 text-slate-950 border-amber-400 hover:bg-amber-400'
                  : 'bg-cyan-600 text-white border-cyan-500 hover:bg-cyan-500'
              )}
              title={isPlaying ? 'Pause' : 'Play (800ms / step)'}
            >
              {isPlaying ? (
                <>
                  <Pause className="w-3.5 h-3.5 fill-current" />
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Play</span>
                </>
              )}
            </button>
            <button
              onClick={handleStepForward}
              disabled={currentStep >= totalSteps}
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 text-slate-300 transition-colors disabled:opacity-40 disabled:pointer-events-none"
              title="Step Forward"
            >
              <SkipForward className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* HTML Range Scrubber */}
          <div className="flex-1 flex items-center gap-3">
            <span className="text-[10px] font-mono text-slate-500 shrink-0">
              1
            </span>
            <input
              type="range"
              min={1}
              max={totalSteps}
              value={currentStep}
              onChange={(e) => {
                setIsPlaying(false);
                setCurrentStep(Number(e.target.value));
              }}
              className="flex-1 h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 focus:outline-none"
            />
            <span className="text-[10px] font-mono text-slate-500 shrink-0">
              {totalSteps}
            </span>
          </div>
        </div>
      </div>

      {/* Synchronized Chronological Event Feed */}
      <div className="max-h-48 overflow-y-auto divide-y divide-slate-800/60 font-mono text-xs bg-slate-950/40">
        {sortedNodes.map((node, idx) => {
          const stepNum = idx + 1;
          const isCurrent = stepNum === currentStep;
          const isPast = stepNum < currentStep;
          const isFuture = stepNum > currentStep;

          const offsetSec = (
            (new Date(node.started_at).getTime() - startTimeMs) /
            1000
          ).toFixed(2);

          let TypeIcon = Bot;
          let iconColor = 'text-indigo-400';
          if (node.span_type === 'LLM') {
            TypeIcon = Cpu;
            iconColor = 'text-purple-400';
          } else if (node.span_type === 'TOOL') {
            TypeIcon = Wrench;
            iconColor = 'text-amber-400';
          } else if (node.span_type === 'APPROVAL') {
            TypeIcon = ShieldAlert;
            iconColor = 'text-rose-400';
          }

          // Historical status for feed
          const endedMs = node.ended_at
            ? new Date(node.ended_at).getTime()
            : null;
          const currentTimestamp = new Date(activeNode.started_at).getTime();
          let displayStatus = node.status;
          if (isCurrent || isPast) {
            if (endedMs === null || endedMs > currentTimestamp) {
              displayStatus = 'RUNNING';
            }
          }

          return (
            <div
              key={node.id}
              ref={isCurrent ? activeEventRef : null}
              onClick={() => {
                setIsPlaying(false);
                setCurrentStep(stepNum);
              }}
              className={cn(
                'px-3.5 py-2 flex items-center justify-between gap-3 cursor-pointer transition-colors text-[11px]',
                isCurrent &&
                  'bg-cyan-950/40 border-l-2 border-cyan-400 text-slate-100 font-semibold',
                isPast && 'hover:bg-slate-900/60 text-slate-300',
                isFuture && 'text-slate-600 opacity-60 hover:opacity-90'
              )}
            >
              {/* Left Column: Step #, Relative Offset, Icon, Type, Operation */}
              <div className="flex items-center gap-2.5 min-w-0">
                <span
                  className={cn(
                    'w-6 text-[10px] shrink-0 font-bold',
                    isCurrent ? 'text-cyan-400' : 'text-slate-500'
                  )}
                >
                  #{stepNum}
                </span>

                <span className="w-12 text-[10px] text-slate-400 shrink-0 flex items-center gap-0.5">
                  <Clock className="w-2.5 h-2.5 text-slate-500" />
                  +{offsetSec}s
                </span>

                <div className={cn('shrink-0 p-1 rounded bg-slate-900 border border-slate-800', iconColor)}>
                  <TypeIcon className="w-3 h-3" />
                </div>

                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-[10px] px-1 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60 uppercase shrink-0">
                    {node.span_type}
                  </span>
                  <span className="font-semibold text-slate-200 truncate" title={node.operation_name}>
                    {node.operation_name}
                  </span>
                  <span className="text-[10px] text-slate-500 truncate" title={node.agent_id}>
                    ({node.agent_id})
                  </span>
                </div>
              </div>

              {/* Right Column: Cost / Error / Status Badge */}
              <div className="flex items-center gap-2 shrink-0">
                {node.error_class && (
                  <span
                    className="flex items-center gap-1 text-[10px] text-rose-400 bg-rose-950/40 border border-rose-800/40 px-1.5 py-0.5 rounded max-w-[120px] truncate"
                    title={node.error_message || node.error_class}
                  >
                    <AlertCircle className="w-2.5 h-2.5 shrink-0" />
                    <span className="truncate">{node.error_class}</span>
                  </span>
                )}

                {node.span_type === 'LLM' && node.direct_cost_usd !== null && node.direct_cost_usd !== undefined && (
                  <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                    <Coins className="w-2.5 h-2.5 text-emerald-500" />
                    ${Number(node.direct_cost_usd).toFixed(4)}
                  </span>
                )}

                <span
                  className={cn(
                    'px-1.5 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider border',
                    isFuture
                      ? 'bg-slate-900 text-slate-600 border-slate-800'
                      : displayStatus === 'RUNNING'
                      ? 'bg-sky-500/20 text-sky-300 border-sky-500/40 animate-pulse'
                      : displayStatus === 'SUCCEEDED'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : displayStatus === 'FAILED' || displayStatus === 'TIMED_OUT'
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  )}
                >
                  {isFuture ? 'QUEUED' : displayStatus}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
