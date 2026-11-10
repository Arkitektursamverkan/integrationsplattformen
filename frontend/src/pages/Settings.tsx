import { useState } from "react";
import {
  Autocomplete, Box, Button, Card, CardContent, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from "@mui/material";
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  ContentCopy as ContentCopyIcon,
} from "@mui/icons-material";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { setTokens } from "@/api/auth";
import { useFlows, type Flow } from "@/api/flows";
import { useSnackbar } from "notistack";
import { copyToClipboard } from "@/utils/clipboard";

interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  enabled: boolean;
  expires_at: string | null;
  created_at: string;
}

interface CreatedKey {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
  scopes: string[];
}

export default function Settings() {
  const { enqueueSnackbar } = useSnackbar();
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [keyName, setKeyName] = useState("");
  // Empty = the key may read every flow; otherwise only these (flow:<id> scopes).
  const [keyFlows, setKeyFlows] = useState<Flow[]>([]);
  const { data: flows } = useFlows();
  const flowName = (scope: string) => {
    if (!scope.startsWith("flow:")) return scope;
    const id = scope.slice(5);
    return `flow: ${flows?.find((f) => f.id === id)?.name ?? id}`;
  };
  const [createdKey, setCreatedKey] = useState<CreatedKey | null>(null);

  const { data: keys } = useQuery<ApiKey[]>({
    queryKey: ["api-keys"],
    queryFn: () => client.get("/api-keys").then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: ({ name, flowIds }: { name: string; flowIds: string[] }) =>
      client.post("/api-keys", { name, scopes: ["data:read", ...flowIds.map((id) => `flow:${id}`)] })
        .then((r) => r.data),
    onSuccess: (data: CreatedKey) => {
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      setCreatedKey(data);
      setKeyName("");
      setKeyFlows([]);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/api-keys/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  const handleCopy = async (key: string) => {
    const ok = await copyToClipboard(key);
    enqueueSnackbar(
      ok ? "API key copied to clipboard" : "Could not copy — select the key and press Ctrl+C",
      { variant: ok ? "info" : "warning" },
    );
  };

  // Change password
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const changePasswordMutation = useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) =>
      client.put("/auth/me/password", data).then((r) => r.data),
  });

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      enqueueSnackbar("New passwords do not match", { variant: "error" });
      return;
    }
    if (newPassword.length < 8) {
      enqueueSnackbar("Password must be at least 8 characters", { variant: "error" });
      return;
    }
    try {
      const svar = await changePasswordMutation.mutateAsync({ current_password: currentPassword, new_password: newPassword });
      // Bytet gör alla tidigare token ogiltiga; svaret har nya för den här sessionen.
      if (svar?.access_token) setTokens(svar);
      enqueueSnackbar("Password changed", { variant: "success" });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      enqueueSnackbar(err.response?.data?.detail || "Failed to change password", { variant: "error" });
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Settings</Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Change Password</Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, maxWidth: 400 }}>
            <TextField label="Current Password" type="password" size="small" fullWidth
              value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            <TextField label="New Password" type="password" size="small" fullWidth
              value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
              helperText="Minimum 8 characters" />
            <TextField label="Confirm New Password" type="password" size="small" fullWidth
              value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            <Button variant="contained" onClick={handleChangePassword} sx={{ alignSelf: "flex-start" }}
              disabled={!currentPassword || !newPassword || !confirmPassword || changePasswordMutation.isPending}>
              {changePasswordMutation.isPending ? "Changing..." : "Change Password"}
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="h5">Consumer API Keys</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setDialogOpen(true)}>
          New API Key
        </Button>
      </Box>

      <TableContainer component={Card}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Prefix</TableCell>
              <TableCell>Scopes</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {keys?.length === 0 && <TableRow><TableCell colSpan={5}>No API keys.</TableCell></TableRow>}
            {keys?.map((k) => (
              <TableRow key={k.id}>
                <TableCell>{k.name}</TableCell>
                <TableCell sx={{ fontFamily: "monospace" }}>{k.key_prefix}...</TableCell>
                <TableCell>{k.scopes.map(flowName).join(", ")}</TableCell>
                <TableCell>{new Date(k.created_at).toLocaleDateString()}</TableCell>
                <TableCell align="right">
                  <IconButton size="small" color="error" onClick={() => deleteMutation.mutate(k.id)}>
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Create Key Dialog */}
      <Dialog open={dialogOpen} onClose={() => { setDialogOpen(false); setCreatedKey(null); }} maxWidth="sm" fullWidth>
        <DialogTitle>{createdKey ? "API Key Created" : "New API Key"}</DialogTitle>
        <DialogContent>
          {!createdKey ? (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
              <TextField
                label="Key Name" fullWidth required
                value={keyName} onChange={(e) => setKeyName(e.target.value)}
                placeholder="e.g. EA Application Production"
              />
              <Autocomplete
                multiple
                options={flows ?? []}
                getOptionLabel={(f) => f.name}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                value={keyFlows}
                onChange={(_, v) => setKeyFlows(v)}
                renderInput={(params) => (
                  <TextField {...params} label="Limit to flows (optional)"
                    helperText="Empty = the key can read the data of every flow." />
                )}
              />
            </Box>
          ) : (
            <Box>
              <Typography variant="body2" gutterBottom sx={{ color: "warning.main" }}>
                Copy this key now — it will not be shown again.
              </Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1, p: 1, bgcolor: "grey.100", borderRadius: 1 }}>
                <Typography sx={{ fontFamily: "monospace", fontSize: 14, flexGrow: 1, wordBreak: "break-all" }}>
                  {createdKey.key}
                </Typography>
                <IconButton size="small" onClick={() => handleCopy(createdKey.key)}>
                  <ContentCopyIcon />
                </IconButton>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          {!createdKey ? (
            <>
              <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button variant="contained" onClick={() => createMutation.mutate({ name: keyName, flowIds: keyFlows.map((f) => f.id) })} disabled={!keyName}>Create</Button>
            </>
          ) : (
            <Button variant="contained" onClick={() => { setDialogOpen(false); setCreatedKey(null); }}>Done</Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
