import { Box, Card, CardContent, Chip, IconButton, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from "@mui/material";
import {
  Delete as DeleteIcon,
  PlayArrow as PlayArrowIcon,
} from "@mui/icons-material";
import { useSchedules, useDeleteSchedule, useUpdateSchedule } from "@/api/schedules";
import { useFlows, useExecuteFlow } from "@/api/flows";
import { useNavigate } from "react-router-dom";
import { useSnackbar } from "notistack";
import { describeCron } from "@/components/common/CronBuilder";

export default function Schedules() {
  const { data: schedules, isLoading } = useSchedules();
  const { data: flows } = useFlows();
  const deleteSchedule = useDeleteSchedule();
  const updateSchedule = useUpdateSchedule();
  const executeFlow = useExecuteFlow();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const flowMap = new Map((flows || []).map((f) => [f.id, f]));

  const active = (schedules || []).filter((s) => s.enabled).length;
  const paused = (schedules || []).filter((s) => !s.enabled).length;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Schedules</Typography>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 3 }}>
        Overview of all scheduled flow executions. Toggle schedules on/off or run flows manually.
      </Typography>

      {/* Stats */}
      <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
        <Chip label={`${(schedules || []).length} total`} variant="outlined" />
        <Chip label={`${active} active`} color="success" size="small" />
        {paused > 0 && <Chip label={`${paused} paused`} color="default" size="small" />}
      </Stack>

      {isLoading ? (
        <Typography>Loading...</Typography>
      ) : !schedules?.length ? (
        <Card>
          <CardContent>
            <Typography sx={{ color: "text.secondary" }}>
              No schedules configured yet. Go to a Flow's detail page to add a schedule.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <TableContainer component={Card}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Flow</TableCell>
                <TableCell>Schedule</TableCell>
                <TableCell>Cron</TableCell>
                <TableCell>Timezone</TableCell>
                <TableCell>Last run</TableCell>
                <TableCell>Next run</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schedules.map((s) => {
                const flow = flowMap.get(s.flow_id);
                return (
                  <TableRow key={s.id} hover>
                    <TableCell>
                      <Switch
                        size="small"
                        checked={s.enabled}
                        onChange={async () => {
                          try {
                            await updateSchedule.mutateAsync({ id: s.id, enabled: !s.enabled });
                            enqueueSnackbar(s.enabled ? "Schedule paused" : "Schedule activated", { variant: "success" });
                          } catch {
                            enqueueSnackbar("Failed to update", { variant: "error" });
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}
                        onClick={() => navigate(`/flows/${s.flow_id}`)}
                      >
                        {flow?.name || s.flow_id.slice(0, 8)}
                      </Typography>
                      {flow && (
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>
                          {flow.enabled ? "Enabled" : "Disabled"}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {describeCron(s.cron_expression) || s.cron_expression}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{s.cron_expression}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">{s.timezone}</Typography>
                    </TableCell>
                    <TableCell>
                      {s.last_run_at ? (
                        <Typography variant="caption">{new Date(s.last_run_at).toLocaleString()}</Typography>
                      ) : (
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>Never</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      {s.next_run_at ? (
                        <Typography variant="caption">{new Date(s.next_run_at).toLocaleString()}</Typography>
                      ) : (
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>—</Typography>
                      )}
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Run flow now">
                        <IconButton
                          size="small"
                          color="primary"
                          onClick={async () => {
                            try {
                              const result = await executeFlow.mutateAsync(s.flow_id);
                              enqueueSnackbar(
                                result.status === "success"
                                  ? `Success: ${result.records_processed} records`
                                  : `Error: ${result.error_message || "Unknown"}`,
                                { variant: result.status === "success" ? "success" : "error" },
                              );
                            } catch {
                              enqueueSnackbar("Execution failed", { variant: "error" });
                            }
                          }}
                        >
                          <PlayArrowIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete schedule">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={async () => {
                            try {
                              await deleteSchedule.mutateAsync(s.id);
                              enqueueSnackbar("Schedule deleted", { variant: "success" });
                            } catch {
                              enqueueSnackbar("Failed to delete", { variant: "error" });
                            }
                          }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
