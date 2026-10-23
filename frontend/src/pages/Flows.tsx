import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Button, Card, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, MenuItem, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from "@mui/material";
import {
  Add as AddIcon,
  PlayArrow as PlayArrowIcon,
  Delete as DeleteIcon,
} from "@mui/icons-material";
import { useFlows, useCreateFlow, useDeleteFlow, useExecuteFlow, type FlowCreate } from "@/api/flows";
import { useConnections } from "@/api/connections";
import StatusChip from "@/components/common/StatusChip";
import { useSnackbar } from "notistack";

export default function Flows() {
  const navigate = useNavigate();
  const { data: flows, isLoading } = useFlows();
  const { data: connections } = useConnections();
  const createMutation = useCreateFlow();
  const deleteMutation = useDeleteFlow();
  const executeMutation = useExecuteFlow();
  const { enqueueSnackbar } = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FlowCreate>({ name: "", connection_id: "", steps: [] });

  const handleCreate = async () => {
    try {
      await createMutation.mutateAsync(form);
      enqueueSnackbar("Flow created", { variant: "success" });
      setDialogOpen(false);
      setForm({ name: "", connection_id: "", steps: [] });
    } catch {
      enqueueSnackbar("Failed to create flow", { variant: "error" });
    }
  };

  const handleExecute = async (id: string) => {
    try {
      const result = await executeMutation.mutateAsync(id);
      enqueueSnackbar(`Execution ${result.status}: ${result.records_processed} records`, {
        variant: result.status === "success" ? "success" : "error",
      });
    } catch {
      enqueueSnackbar("Execution failed", { variant: "error" });
    }
  };

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h4">Flows</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setDialogOpen(true)}>
          New Flow
        </Button>
      </Box>

      <TableContainer component={Card}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Connection</TableCell>
              <TableCell>Enabled</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={5}>Loading...</TableCell></TableRow>}
            {flows?.length === 0 && <TableRow><TableCell colSpan={5}>No flows yet.</TableCell></TableRow>}
            {flows?.map((flow) => {
              const conn = connections?.find((c) => c.id === flow.connection_id);
              return (
                <TableRow key={flow.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/flows/${flow.id}`)}>
                  <TableCell>{flow.name}</TableCell>
                  <TableCell>{conn?.name || flow.connection_id}</TableCell>
                  <TableCell><StatusChip status={flow.enabled ? "active" : "disabled"} /></TableCell>
                  <TableCell>{new Date(flow.created_at).toLocaleDateString()}</TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <IconButton size="small" onClick={() => handleExecute(flow.id)} title="Execute now">
                      <PlayArrowIcon />
                    </IconButton>
                    <IconButton size="small" color="error" onClick={() => deleteMutation.mutate(flow.id)} title="Delete">
                      <DeleteIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Flow</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
          <TextField
            label="Name" fullWidth required
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <TextField
            label="Description" fullWidth multiline rows={2}
            value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <TextField
            label="Connection" select fullWidth required
            value={form.connection_id}
            onChange={(e) => setForm({ ...form, connection_id: e.target.value })}
          >
            {connections?.map((c) => <MenuItem key={c.id} value={c.id}>{c.name} ({c.connector_type})</MenuItem>)}
          </TextField>
          <TextField
            label="Steps (JSON)" fullWidth multiline rows={6}
            placeholder='[{"step_order": 0, "step_type": "transform", "config": {"mappings": [...]}}]'
            value={JSON.stringify(form.steps, null, 2)}
            onChange={(e) => {
              try { setForm({ ...form, steps: JSON.parse(e.target.value) }); } catch { /* ignore */ }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate} disabled={!form.name || !form.connection_id}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
