'use client';

import { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Edge,
  type NodeTypes,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { Network } from 'lucide-react';
import { LineageGraphDTO, LineageNodeDTO } from '@/types/telemetry';
import { SpanNode, type SpanNodeType } from './SpanNode';

const NODE_WIDTH = 256;
const NODE_HEIGHT = 100;

const nodeTypes: NodeTypes = {
  spanNode: SpanNode,
};

interface LineageGraphProps {
  graph: LineageGraphDTO;
  selectedSpanId?: string | null;
  onSelectSpan: (span: LineageNodeDTO | null) => void;
}

function getLayoutedElements(
  nodes: LineageNodeDTO[],
  edges: LineageGraphDTO['edges'],
  selectedSpanId?: string | null
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
    dagreGraph.setEdge(edge.source, edge.target);
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
      selected: node.id === selectedSpanId,
    };
  });

  const flowEdges: Edge[] = edges.map((edge) => {
    const targetNode = nodeMap.get(edge.target);
    const sourceNode = nodeMap.get(edge.source);

    const isFailed =
      edge.is_failed_path ||
      targetNode?.status === 'FAILED' ||
      targetNode?.status === 'TIMED_OUT';

    const isRunning =
      targetNode?.status === 'RUNNING' || sourceNode?.status === 'RUNNING';

    const isAwaiting = targetNode?.status === 'AWAITING_APPROVAL';

    let strokeColor = '#475569'; // slate-600
    let animated = false;

    if (isFailed) {
      strokeColor = '#f43f5e'; // crimson / rose-500
    } else if (isRunning) {
      strokeColor = '#38bdf8'; // sky-400
      animated = true;
    } else if (isAwaiting) {
      strokeColor = '#f59e0b'; // amber-500
      animated = true;
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      animated,
      style: {
        stroke: strokeColor,
        strokeWidth: isFailed || isRunning ? 2 : 1.5,
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
}: LineageGraphProps) {
  const { flowNodes, flowEdges } = useMemo(
    () => getLayoutedElements(graph.nodes, graph.edges, selectedSpanId),
    [graph.nodes, graph.edges, selectedSpanId]
  );

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
      <div className="flex flex-col items-center justify-center h-full w-full bg-slate-950/90 text-slate-500 font-mono text-sm border border-slate-900 rounded-xl">
        <Network className="w-10 h-10 mb-3 text-slate-700 animate-pulse" />
        <span className="text-slate-400 font-medium">No spans recorded yet</span>
        <span className="text-xs text-slate-600 mt-1">
          Awaiting telemetry events for run {graph.run_id}...
        </span>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative bg-slate-950 rounded-xl overflow-hidden border border-slate-900">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
        minZoom={0.2}
        maxZoom={2.0}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#334155" gap={20} size={1} />
        <Controls className="!bg-slate-900/95 !border-slate-800 !text-slate-300 [&>button]:!border-slate-800 [&>button]:!bg-slate-900 [&>button:hover]:!bg-slate-800 [&>button]:!text-slate-300" />
        <MiniMap
          className="!bg-slate-950/90 !border-slate-800 rounded-lg overflow-hidden shadow-2xl"
          maskColor="rgba(15, 23, 42, 0.7)"
          nodeColor={(n) => {
            const st = (n.data as unknown as LineageNodeDTO)?.status;
            if (st === 'FAILED' || st === 'TIMED_OUT') return '#f43f5e';
            if (st === 'RUNNING') return '#38bdf8';
            if (st === 'AWAITING_APPROVAL') return '#f59e0b';
            if (st === 'SUCCEEDED') return '#10b981';
            return '#64748b';
          }}
        />
      </ReactFlow>
    </div>
  );
}
