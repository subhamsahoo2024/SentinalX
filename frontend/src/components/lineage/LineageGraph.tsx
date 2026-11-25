'use client';

import { useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  type Edge,
  type NodeTypes,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { Network } from 'lucide-react';
import { useTheme } from '@/hooks/use-theme';
import { LineageGraphDTO, LineageNodeDTO } from '@/types/telemetry';
import { SpanNode, type SpanNodeType } from './SpanNode';

const NODE_WIDTH = 256;
const NODE_HEIGHT = 125;

const nodeTypes: NodeTypes = {
  spanNode: SpanNode,
};

interface LineageGraphProps {
  graph: LineageGraphDTO;
  selectedSpanId?: string | null;
  onSelectSpan: (span: LineageNodeDTO | null) => void;
  impactedSpanIds?: string[];
}

function getLayoutedElements(
  nodes: LineageNodeDTO[],
  edges: LineageGraphDTO['edges'],
  isDark: boolean,
  selectedSpanId?: string | null,
  impactedSpanIds?: string[]
): { flowNodes: SpanNodeType[]; flowEdges: Edge[] } {
  if (nodes.length === 0) {
    return { flowNodes: [], flowEdges: [] };
  }

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: 'TB',
    nodesep: 50,
    ranksep: 80,
  });

  const nodeMap = new Map<string, LineageNodeDTO>();
  nodes.forEach((node) => {
    nodeMap.set(node.id, node);
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    if (nodeMap.has(edge.source) && nodeMap.has(edge.target)) {
      dagreGraph.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(dagreGraph);

  const flowNodes: SpanNodeType[] = nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);
    const x = dagreNode ? dagreNode.x - NODE_WIDTH / 2 : 0;
    const y = dagreNode ? dagreNode.y - NODE_HEIGHT / 2 : 0;

    return {
      id: node.id,
      type: 'spanNode',
      position: { x, y },
      data: node,
      selected: node.id === selectedSpanId || node.span_id === selectedSpanId,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      initialWidth: NODE_WIDTH,
      initialHeight: NODE_HEIGHT,
      style: { width: NODE_WIDTH, height: NODE_HEIGHT, visibility: 'visible' },
    };
  });

  const flowEdges: Edge[] = edges.map((edge) => {
    const targetNode = nodeMap.get(edge.target);
    const sourceNode = nodeMap.get(edge.source);

    const isBlastRadius =
      edge.is_failed_path ||
      Boolean(impactedSpanIds && impactedSpanIds.includes(edge.target));

    const isFailed =
      isBlastRadius ||
      targetNode?.status === 'FAILED' ||
      targetNode?.status === 'TIMED_OUT';

    const isRunning =
      targetNode?.status === 'RUNNING' || sourceNode?.status === 'RUNNING';

    const isAwaiting = targetNode?.status === 'AWAITING_APPROVAL';

    const isStalled =
      targetNode?.status === 'STALLED' || sourceNode?.status === 'STALLED';

    let strokeColor = isDark ? '#475569' : '#94a3b8';
    let animated = false;
    let strokeWidth = isFailed || isRunning ? 2 : 1.5;

    if (isBlastRadius) {
      strokeColor = isDark ? '#f43f5e' : '#e11d48';
      strokeWidth = 2.5;
      animated = true;
    } else if (isFailed) {
      strokeColor = isDark ? '#f43f5e' : '#e11d48';
      strokeWidth = 2;
    } else if (isRunning) {
      strokeColor = isDark ? '#38bdf8' : '#0284c7';
      animated = true;
    } else if (isAwaiting) {
      strokeColor = isDark ? '#f59e0b' : '#d97706';
      animated = true;
    } else if (isStalled) {
      strokeColor = isDark ? '#a855f7' : '#9333ea';
      strokeWidth = 2;
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      animated,
      style: {
        stroke: strokeColor,
        strokeWidth,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 16,
        height: 16,
      },
    };
  });

  return { flowNodes, flowEdges };
}

export function LineageGraph({
  graph,
  selectedSpanId,
  onSelectSpan,
  impactedSpanIds,
}: LineageGraphProps) {
  const { isDark } = useTheme();

  const { flowNodes, flowEdges } = useMemo(
    () =>
      getLayoutedElements(
        graph.nodes,
        graph.edges,
        isDark,
        selectedSpanId,
        impactedSpanIds
      ),
    [graph.nodes, graph.edges, isDark, selectedSpanId, impactedSpanIds]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<SpanNodeType>(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(flowEdges);

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges, setNodes, setEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      onSelectSpan(node.data as unknown as LineageNodeDTO);
    },
    [onSelectSpan]
  );

  const handlePaneClick = useCallback(() => {
    onSelectSpan(null);
  }, [onSelectSpan]);

  if (graph.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[560px] w-full bg-[#F5F9FF] dark:bg-slate-950/90 text-slate-500 font-mono text-sm border border-[#D4E2F4] dark:border-slate-900 rounded-xl">
        <Network className="w-10 h-10 mb-3 text-slate-400 dark:text-slate-700 animate-pulse" />
        <span className="text-slate-700 dark:text-slate-400 font-medium">No spans recorded yet</span>
        <span className="text-xs text-slate-500 dark:text-slate-600 mt-1">
          Awaiting telemetry events for run {graph.run_id}...
        </span>
      </div>
    );
  }

  return (
    <div className="w-full h-[560px] relative bg-[#F5F9FF] dark:bg-slate-950 rounded-xl overflow-hidden border border-[#D4E2F4] dark:border-slate-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
        minZoom={0.2}
        maxZoom={2.0}
        proOptions={{ hideAttribution: true }}
      >
        <Background color={isDark ? '#334155' : '#cbd5e1'} gap={20} size={1} />
        <Controls className="!bg-white/95 !border-[#D4E2F4] !text-slate-700 [&>button]:!border-[#D4E2F4] [&>button]:!bg-white [&>button:hover]:!bg-slate-100 [&>button]:!text-slate-700 dark:!bg-slate-900/95 dark:!border-slate-800 dark:!text-slate-300 dark:[&>button]:!border-slate-800 dark:[&>button]:!bg-slate-900 dark:[&>button:hover]:!bg-slate-800 dark:[&>button]:!text-slate-300" />
        <MiniMap
          className="!bg-white/90 !border-[#D4E2F4] dark:!bg-slate-950/90 dark:!border-slate-800 rounded-lg overflow-hidden shadow-2xl"
          maskColor={isDark ? 'rgba(15, 23, 42, 0.7)' : 'rgba(241, 245, 249, 0.7)'}
          nodeColor={(n) => {
            const st = (n.data as unknown as LineageNodeDTO)?.status;
            if (st === 'FAILED' || st === 'TIMED_OUT') return '#f43f5e';
            if (st === 'RUNNING') return isDark ? '#38bdf8' : '#0284c7';
            if (st === 'AWAITING_APPROVAL') return '#f59e0b';
            if (st === 'STALLED') return '#a855f7';
            if (st === 'SUCCEEDED') return '#10b981';
            return isDark ? '#64748b' : '#94a3b8';
          }}
        />
      </ReactFlow>
    </div>
  );
}
