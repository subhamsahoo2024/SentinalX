'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  X,
} from 'lucide-react';
import { StatusBadge } from '@/components/StatusBadge';
import { cn } from '@/lib/utils';
import type { LineageEdgeDTO, LineageNodeDTO } from '@/types/telemetry';

interface TimelineReplayProps {
  allNodes: LineageNodeDTO[];
  allEdges: LineageEdgeDTO[];
  onReplayFrame: (
    nodes: LineageNodeDTO[],
    edges: LineageEdgeDTO[],
    activeNode: LineageNodeDTO | null,
    isExplicitSelect?: boolean,
  ) => void;
  onExitReplay: () => void;
}

export function TimelineReplay({
  allNodes,
  allEdges,
  onReplayFrame,
  onExitReplay,
}: TimelineReplayProps) {
  const sortedNodes = useMemo(
    () =>
      [...allNodes].sort(
        (a, b) => Date.parse(a.started_at) - Date.parse(b.started_at),
      ),
    [allNodes],
  );

  const totalSteps = sortedNodes.length;
  const [currentStep, setCurrentStep] = useState<number>(totalSteps > 0 ? 1 : 0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const explicitSelectRef = useRef<boolean>(false);

  const traceStartMs = useMemo(() => {
    if (sortedNodes.length === 0) return 0;
    return Date.parse(sortedNodes[0].started_at);
  }, [sortedNodes]);

  useEffect(() => {
    if (!isPlaying || totalSteps === 0) return;
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
  }, [isPlaying, totalSteps]);

  useEffect(() => {
    if (totalSteps === 0 || currentStep <= 0) {
      onReplayFrame([], [], null);
      return;
    }

    const activeNode = sortedNodes[currentStep - 1] ?? null;
    const activeTimeMs = activeNode ? Date.parse(activeNode.started_at) : Infinity;

    const visibleNodes = sortedNodes.slice(0, currentStep).map((node) => {
      const endedMs = node.ended_at ? Date.parse(node.ended_at) : null;
      const stillRunningAtStep = endedMs !== null && endedMs > activeTimeMs;
      return stillRunningAtStep
        ? { ...node, status: 'RUNNING' }
        : node;
    });

    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = allEdges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
    );

    const isExplicit = explicitSelectRef.current;
    explicitSelectRef.current = false;
    onReplayFrame(visibleNodes, visibleEdges, activeNode, isExplicit);
  }, [currentStep, sortedNodes, allEdges, totalSteps, onReplayFrame]);

  if (totalSteps === 0) return null;

  return (
    <div className="rounded-lg border border-[#93C5FD] dark:border-[#1D3868] bg-white dark:bg-[#07152E] p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xs font-semibold text-[#061838] dark:text-slate-100">
            Execution Timeline Replay
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 font-mono tabular-nums">
            Step {currentStep} of {totalSteps}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              setCurrentStep(1);
            }}
            className="rounded-md border border-slate-200 dark:border-[#1D3868] p-1.5 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247]"
            aria-label="Reset replay"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            disabled={currentStep <= 1}
            onClick={() => {
              setIsPlaying(false);
              setCurrentStep((s) => Math.max(1, s - 1));
            }}
            className="rounded-md border border-slate-200 dark:border-[#1D3868] p-1.5 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247] disabled:opacity-40"
            aria-label="Step back"
          >
            <SkipBack className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => {
              if (currentStep >= totalSteps && !isPlaying) {
                setCurrentStep(1);
              }
              setIsPlaying((p) => !p);
            }}
            className="inline-flex items-center gap-1.5 rounded-md bg-[#0257D5] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#0346B0]"
          >
            {isPlaying ? (
              <>
                <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Pause</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Play</span>
              </>
            )}
          </button>
          <button
            type="button"
            disabled={currentStep >= totalSteps}
            onClick={() => {
              setIsPlaying(false);
              setCurrentStep((s) => Math.min(totalSteps, s + 1));
            }}
            className="rounded-md border border-slate-200 dark:border-[#1D3868] p-1.5 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247] disabled:opacity-40"
            aria-label="Step forward"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onExitReplay}
            className="ml-2 inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-[#1D3868] px-2.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-[#0D2247]"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Exit Replay</span>
          </button>
        </div>
      </div>

      <input
        type="range"
        min={1}
        max={totalSteps}
        value={currentStep}
        onChange={(e) => {
          setIsPlaying(false);
          setCurrentStep(Number(e.target.value));
        }}
        aria-label="Replay step scrubber"
        className="w-full accent-[#0257D5] dark:accent-[#00C2FF] cursor-pointer"
      />

      <div className="max-h-36 overflow-y-auto divide-y divide-slate-100 dark:divide-[#15284B] border border-[#D4E2F4] dark:border-[#172E56] rounded-md">
        {sortedNodes.map((node, idx) => {
          const stepNum = idx + 1;
          const isCurrent = stepNum === currentStep;
          const isPast = stepNum < currentStep;
          const relSecs = ((Date.parse(node.started_at) - traceStartMs) / 1000).toFixed(2);

          return (
            <button
              key={node.span_id}
              type="button"
              onClick={() => {
                explicitSelectRef.current = true;
                setIsPlaying(false);
                setCurrentStep(stepNum);
              }}
              className={cn(
                'w-full flex items-center justify-between gap-3 px-3 py-2 text-xs text-left transition-colors',
                isCurrent
                  ? 'bg-[#EFF6FF] font-medium text-[#041533] dark:bg-[#0257D5]/25 dark:text-white'
                  : isPast
                    ? 'bg-white text-slate-700 hover:bg-slate-50 dark:bg-[#07152E] dark:text-slate-200 dark:hover:bg-[#0D2247]'
                    : 'bg-slate-50/70 text-slate-400 hover:bg-slate-100 dark:bg-[#040B18] dark:text-slate-500 dark:hover:bg-[#0A1B3B]',
              )}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="font-mono text-[11px] tabular-nums w-14 shrink-0">
                  +{relSecs}s
                </span>
                <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400 shrink-0">
                  {node.span_type}
                </span>
                <span className="truncate">{node.operation_name}</span>
              </div>
              <StatusBadge status={String(node.status)} compact />
            </button>
          );
        })}
      </div>
    </div>
  );
}
