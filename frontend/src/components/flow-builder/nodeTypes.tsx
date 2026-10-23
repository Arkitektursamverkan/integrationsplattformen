import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Box, Chip, Typography } from "@mui/material";
import {
  Storage as StorageIcon,
  Transform as TransformIcon,
  CloudDownload as CloudDownloadIcon,
  Api as ApiIcon,
} from "@mui/icons-material";

// ── Shared styles ───────────────────────────────────────────────────────────

const nodeBase = (color: string, borderColor: string) => ({
  background: "#fff",
  border: `2px solid ${borderColor}`,
  borderRadius: 8,
  padding: "12px 16px",
  minWidth: 200,
  boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
});

const handleStyle = {
  width: 10,
  height: 10,
  border: "2px solid #fff",
};

// ── SourceNode (blue) ───────────────────────────────────────────────────────

export interface SourceNodeData {
  label: string;
  connectionName?: string;
  connectorType?: string;
  [key: string]: unknown;
}

export const SourceNode = memo(({ data }: NodeProps) => {
  const d = data as SourceNodeData;
  return (
    <Box sx={nodeBase("#e3f2fd", "#1565c0")}>
      <Handle type="source" position={Position.Bottom} style={{ ...handleStyle, background: "#1565c0" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <CloudDownloadIcon sx={{ color: "#1565c0", fontSize: 20 }} />
        <Chip label="SOURCE" size="small" sx={{ bgcolor: "#1565c0", color: "#fff", fontWeight: 700, fontSize: 10, height: 20 }} />
      </Box>
      <Typography variant="subtitle2" fontWeight={600}>{d.label || "Data Source"}</Typography>
      {d.connectionName && (
        <Typography variant="caption" color="text.secondary" display="block">
          {d.connectionName} {d.connectorType ? `(${d.connectorType})` : ""}
        </Typography>
      )}
    </Box>
  );
});
SourceNode.displayName = "SourceNode";

// ── TransformNode (amber) ───────────────────────────────────────────────────

export interface TransformNodeData {
  label: string;
  operationType?: string;
  operationLabel?: string;
  stageIndex?: number;
  [key: string]: unknown;
}

export const TransformNode = memo(({ data }: NodeProps) => {
  const d = data as TransformNodeData;
  return (
    <Box sx={nodeBase("#fff8e1", "#e65100")}>
      <Handle type="target" position={Position.Top} style={{ ...handleStyle, background: "#e65100" }} />
      <Handle type="source" position={Position.Bottom} style={{ ...handleStyle, background: "#e65100" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <TransformIcon sx={{ color: "#e65100", fontSize: 20 }} />
        <Chip
          label={d.operationLabel || d.operationType || "TRANSFORM"}
          size="small"
          sx={{ bgcolor: "#e65100", color: "#fff", fontWeight: 700, fontSize: 10, height: 20 }}
        />
        {d.stageIndex != null && (
          <Typography variant="caption" color="text.secondary">Stage {d.stageIndex + 1}</Typography>
        )}
      </Box>
      <Typography variant="subtitle2" fontWeight={600}>{d.label || "Transform"}</Typography>
    </Box>
  );
});
TransformNode.displayName = "TransformNode";

// ── StoreNode (green) ───────────────────────────────────────────────────────

export interface StoreNodeData {
  label: string;
  recordCount?: number;
  [key: string]: unknown;
}

export const StoreNode = memo(({ data }: NodeProps) => {
  const d = data as StoreNodeData;
  return (
    <Box sx={nodeBase("#e8f5e9", "#2e7d32")}>
      <Handle type="target" position={Position.Top} style={{ ...handleStyle, background: "#2e7d32" }} />
      <Handle type="source" position={Position.Bottom} style={{ ...handleStyle, background: "#2e7d32" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <StorageIcon sx={{ color: "#2e7d32", fontSize: 20 }} />
        <Chip label="STORE" size="small" sx={{ bgcolor: "#2e7d32", color: "#fff", fontWeight: 700, fontSize: 10, height: 20 }} />
        {d.recordCount != null && (
          <Chip label={`${d.recordCount} records`} size="small" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
        )}
      </Box>
      <Typography variant="subtitle2" fontWeight={600}>{d.label || "Data Store"}</Typography>
    </Box>
  );
});
StoreNode.displayName = "StoreNode";

// ── EndpointNode (purple) ───────────────────────────────────────────────────

export interface EndpointNodeData {
  label: string;
  apiUrl?: string;
  [key: string]: unknown;
}

export const EndpointNode = memo(({ data }: NodeProps) => {
  const d = data as EndpointNodeData;
  return (
    <Box sx={nodeBase("#f3e5f5", "#7b1fa2")}>
      <Handle type="target" position={Position.Top} style={{ ...handleStyle, background: "#7b1fa2" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <ApiIcon sx={{ color: "#7b1fa2", fontSize: 20 }} />
        <Chip label="API ENDPOINT" size="small" sx={{ bgcolor: "#7b1fa2", color: "#fff", fontWeight: 700, fontSize: 10, height: 20 }} />
      </Box>
      <Typography variant="subtitle2" fontWeight={600}>{d.label || "Data API"}</Typography>
      {d.apiUrl && (
        <Typography variant="caption" fontFamily="monospace" color="text.secondary" display="block" sx={{ mt: 0.5, wordBreak: "break-all" }}>
          {d.apiUrl}
        </Typography>
      )}
    </Box>
  );
});
EndpointNode.displayName = "EndpointNode";

// ── Registry ────────────────────────────────────────────────────────────────

export const NODE_TYPES = {
  source: SourceNode,
  transform: TransformNode,
  store: StoreNode,
  endpoint: EndpointNode,
};
