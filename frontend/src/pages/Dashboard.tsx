import { Box, Card, CardContent, Grid, Typography } from "@mui/material";
import CableIcon from "@mui/icons-material/Cable";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import { useConnections } from "@/api/connections";
import { useFlows } from "@/api/flows";
import { useExecutions } from "@/api/executions";
import StatusChip from "@/components/common/StatusChip";

function StatCard({ title, value, icon, color }: { title: string; value: number | string; icon: React.ReactNode; color: string }) {
  return (
    <Card>
      <CardContent sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{ color, fontSize: 40, display: "flex" }}>{icon}</Box>
        <Box>
          <Typography variant="h4">{value}</Typography>
          <Typography variant="body2" color="text.secondary">{title}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const { data: connections } = useConnections();
  const { data: flows } = useFlows();
  const { data: executions } = useExecutions({ page: 1 });

  const activeConnections = connections?.filter((c) => c.status === "active").length ?? 0;
  const enabledFlows = flows?.filter((f) => f.enabled).length ?? 0;
  const recentSuccess = executions?.executions.filter((e) => e.status === "success").length ?? 0;
  const recentErrors = executions?.executions.filter((e) => e.status === "error").length ?? 0;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Dashboard</Typography>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard title="Active Connections" value={activeConnections} icon={<CableIcon fontSize="inherit" />} color="#1565c0" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard title="Enabled Flows" value={enabledFlows} icon={<AccountTreeIcon fontSize="inherit" />} color="#7b1fa2" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard title="Recent Successes" value={recentSuccess} icon={<CheckCircleIcon fontSize="inherit" />} color="#2e7d32" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard title="Recent Errors" value={recentErrors} icon={<ErrorIcon fontSize="inherit" />} color="#d32f2f" />
        </Grid>
      </Grid>

      <Typography variant="h5" gutterBottom>Recent Executions</Typography>
      <Card>
        <CardContent>
          {executions?.executions.length === 0 && (
            <Typography color="text.secondary">No executions yet. Create a flow and run it to see results here.</Typography>
          )}
          {executions?.executions.slice(0, 10).map((exec) => (
            <Box key={exec.id} sx={{ display: "flex", alignItems: "center", gap: 2, py: 1, borderBottom: "1px solid #eee" }}>
              <StatusChip status={exec.status} />
              <Typography variant="body2" sx={{ minWidth: 80 }}>{exec.trigger_type}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
                {new Date(exec.started_at).toLocaleString()}
              </Typography>
              <Typography variant="body2">
                {exec.records_processed} records ({exec.records_created} new, {exec.records_updated} updated)
              </Typography>
            </Box>
          ))}
        </CardContent>
      </Card>
    </Box>
  );
}
