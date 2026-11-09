import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Box, Button, Card, CardContent, Divider, Link, TextField, Typography, Alert } from "@mui/material";
import { useLogin, useSetupStatus, setTokens } from "@/api/auth";
import { completeEntraLogin, fetchEntraConfig, startEntraLogin } from "@/api/entra";

export default function Login() {
  const navigate = useNavigate();
  const loginMutation = useLogin();
  const setup = useSetupStatus();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [entraBusy, setEntraBusy] = useState(false);
  const { data: entra } = useQuery({ queryKey: ["entra-config"], queryFn: fetchEntraConfig, retry: false });

  // Tillbaka från Microsoft: byt svaret mot plattformens tokens.
  useEffect(() => {
    if (!entra) return;
    setEntraBusy(true);
    completeEntraLogin(entra)
      .then((tokens) => {
        if (tokens) {
          setTokens(tokens);
          navigate("/");
        }
      })
      .catch((e: any) => setError(e?.response?.data?.detail || e?.message || "Inloggningen med Microsoft misslyckades"))
      .finally(() => setEntraBusy(false));
  }, [entra, navigate]);

  // A fresh installation has no accounts yet: go straight to creating the first one.
  useEffect(() => {
    if (setup.data?.needed) navigate("/setup", { replace: true });
  }, [setup.data?.needed, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const tokens = await loginMutation.mutateAsync({ username, password });
      setTokens(tokens);
      navigate("/");
    } catch {
      setError("Fel användarnamn eller lösenord");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "grey.100" }}>
      <Card sx={{ maxWidth: 400, width: "100%" }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>Integrationsplattformen</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 3 }}>Logga in för att hantera integrationerna</Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          {entra && (
            <>
              <Button variant="contained" fullWidth size="large" disabled={entraBusy}
                onClick={() => {
                  setError("");
                  setEntraBusy(true);
                  startEntraLogin(entra).catch((e: any) => {
                    setError(e?.message || "Inloggningen med Microsoft misslyckades");
                    setEntraBusy(false);
                  });
                }}>
                {entraBusy ? "Loggar in…" : "Logga in med Microsoft"}
              </Button>
              <Divider sx={{ my: 3 }}>eller med ett eget konto</Divider>
            </>
          )}

          <form onSubmit={handleSubmit}>
            <TextField label="Användarnamn" fullWidth required value={username} autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} autoFocus />
            <TextField label="Lösenord" fullWidth required type="password" value={password} autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} sx={{ mb: 3 }} />
            <Button type="submit" variant={entra ? "outlined" : "contained"} fullWidth size="large"
              disabled={loginMutation.isPending || !username || !password}>
              {loginMutation.isPending ? "Loggar in…" : "Logga in"}
            </Button>
          </form>
          {setup.data?.needed && (
            <Typography variant="body2" sx={{ mt: 2 }}>
              Inget konto finns ännu – <Link component={RouterLink} to="/setup">skapa det första</Link>.
            </Typography>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
