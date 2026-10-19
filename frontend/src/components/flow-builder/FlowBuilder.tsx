import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type OnConnect,
  addEdge,
  MarkerType,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Box, Chip, Typography } from "@mui/material";
import { NODE_TYPES } from "./nodeTypes";
import type { FlowStep } from "@/api/flows";
import type { Connection } from "@/api/connections";

// ── Operation label lookup ──────────────────────────────────────────────────

const OP_LABELS: Record<string, string> = {
  transform: "Field Mapping",
  add_column: "Add Column",
  remove: "Remove Fields",
  rename: "Rename Fields",
  filter: "Filter Rows",
  replace: "Find & Replace",
  substring: "Extract Text",
  split_column: "Split Column",
  math: "Math",
  combine: "Combine Fields",
  lookup: "Value Lookup",
  sort: "Sort",
  trim: "Trim",
  deduplicate: "Deduplicate",
};

// ── Build nodes & edges from flow data ──────────────────────────────────────

interface BuildArgs {
  flowId: string;
  flowName: string;
  connection: Connection | undefined;
  steps: FlowStep[];
  recordCount?: number;
}

function buildGraph({ flowId, flowName, connection, steps, recordCount }: BuildArgs): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const X = 300;
  let y = 0;
  const SPACING = 120;

  // Source node
  const sourceId = "source";
  nodes.push({
    id: sourceId,
    type: "source",
    position: { x: X, y },
    data: {
      label: connection?.name || "Source",
      connectionName: connection?.name,
      connectorType: connection?.connector_type,
    },
  });
  y += SPACING;

  // Transform nodes (one per step)
  let prevId = sourceId;
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const nodeId = `transform-${i}`;
    nodes.push({
      id: nodeId,
      type: "transform",
      position: { x: X, y },
      data: {
        label: OP_LABELS[step.step_type] || step.step_type,
        operationType: step.step_type,
        operationLabel: OP_LABELS[step.step_type],
        stageIndex: i,
      },
    });
    edges.push({
      id: `e-${prevId}-${nodeId}`,
      source: prevId,
      target: nodeId,
      animated: true,
      style: { stroke: "#e65100" },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#e65100" },
    });
    prevId = nodeId;
    y += SPACING;
  }

  // Store node
  const storeId = "store";
  nodes.push({
    id: storeId,
    type: "store",
    position: { x: X, y },
    data: {
      label: "Data Store",
      recordCount,
    },
  });
  edges.push({
    id: `e-${prevId}-${storeId}`,
    source: prevId,
    target: storeId,
    animated: true,
    style: { stroke: "#2e7d32" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#2e7d32" },
  });
  y += SPACING;

  // Endpoint node
  const endpointId = "endpoint";
  nodes.push({
    id: endpointId,
    type: "endpoint",
    position: { x: X, y },
    data: {
      label: "Consumer API",
      apiUrl: `GET /api/v1/data/${flowId}/records`,
    },
  });
  edges.push({
    id: `e-${storeId}-${endpointId}`,
    source: storeId,
    target: endpointId,
    style: { stroke: "#7b1fa2" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#7b1fa2" },
  });

  return { nodes, edges };
}

// ── Component ───────────────────────────────────────────────────────────────

interface FlowBuilderProps {
  flowId: string;
  flowName: string;
  connection: Connection | undefined;
  steps: FlowStep[];
  recordCount?: number;
  onNodeClick?: (nodeId: string, stageIndex?: number) => void;
}

export default function FlowBuilder({
  flowId, flowName, connection, steps, recordCount, onNodeClick,
}: FlowBuilderProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildGraph({ flowId, flowName, connection, steps, recordCount }),
    [flowId, flowName, connection, steps, recordCount],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect: OnConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        const stageIndex = node.type === "transform"
          ? (node.data as { stageIndex?: number }).stageIndex
          : undefined;
        onNodeClick(node.id, stageIndex);
      }
    },
    [onNodeClick],
  );

  // Re-sync when steps change
  useMemo(() => {
    const { nodes: n, edges: e } = buildGraph({ flowId, flowName, connection, steps, recordCount });
    setNodes(n);
    setEdges(e);
  }, [flowId, flowName, connection, steps, recordCount, setNodes, setEdges]);

  return (
    <Box sx={{ width: "100%", height: "100%", bgcolor: "#fafafa" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ animated: true }}
      >
        <Background gap={20} size={1} color="#e0e0e0" />
        <Controls position="bottom-right" />
        <MiniMap
          nodeColor={(node) => {
            switch (node.type) {
              case "source": return "#1565c0";
              case "transform": return "#e65100";
              case "store": return "#2e7d32";
              case "endpoint": return "#7b1fa2";
              default: return "#999";
            }
          }}
          style={{ border: "1px solid #ddd" }}
        />
        <Panel position="top-left">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Chip icon={<Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#1565c0" }} />} label="Source" size="small" variant="outlined" />
            <Chip icon={<Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#e65100" }} />} label="Transform" size="small" variant="outlined" />
            <Chip icon={<Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#2e7d32" }} />} label="Store" size="small" variant="outlined" />
            <Chip icon={<Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#7b1fa2" }} />} label="API Endpoint" size="small" variant="outlined" />
          </Box>
        </Panel>
      </ReactFlow>
    </Box>
  );
}
