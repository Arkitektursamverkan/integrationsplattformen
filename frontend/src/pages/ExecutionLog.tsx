import { useState } from "react";
import {
  Box, Card, MenuItem, Pagination, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useExecutions } from "@/api/executions";
import StatusChip from "@/components/common/StatusChip";

export default function ExecutionLog() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const { data, isLoading } = useExecutions({ page, status: statusFilter || undefined });

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h4">Execution Log</Typography>
        <TextField
          select size="small" label="Status" sx={{ minWidth: 150 }}
          value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="success">Success</MenuItem>
          <MenuItem value="error">Error</MenuItem>
          <MenuItem value="running">Running</MenuItem>
        </TextField>
      </Box>

      <TableContainer component={Card}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Status</TableCell>
              <TableCell>Trigger</TableCell>
              <TableCell>Started</TableCell>
              <TableCell>Finished</TableCell>
              <TableCell>Records</TableCell>
              <TableCell>Error</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={6}>Loading...</TableCell></TableRow>}
            {data?.executions.map((exec) => (
              <TableRow key={exec.id}>
                <TableCell><StatusChip status={exec.status} /></TableCell>
                <TableCell>{exec.trigger_type}</TableCell>
                <TableCell>{new Date(exec.started_at).toLocaleString()}</TableCell>
                <TableCell>{exec.finished_at ? new Date(exec.finished_at).toLocaleString() : "-"}</TableCell>
                <TableCell>{exec.records_processed} ({exec.records_created}+{exec.records_updated})</TableCell>
                <TableCell sx={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {exec.error_message || "-"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {data && data.total > data.page_size && (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
          <Pagination
            count={Math.ceil(data.total / data.page_size)}
            page={page}
            onChange={(_, p) => setPage(p)}
          />
        </Box>
      )}
    </Box>
  );
}
