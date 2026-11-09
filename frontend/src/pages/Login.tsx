import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, Link, TextField, Typography, Alert } from "@mui/material";
import { useLogin, useSetupNeeded, setTokens } from "@/api/auth";

export default function Login() {
  const navigate = useNavigate();
  const loginMutation = useLogin();
  const setupNeeded = useSetupNeeded();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  // A fresh installation has no accounts yet: go straight to creating the first one.
  useEffect(() => {
    if (setupNeeded.data) navigate("/setup", { replace: true });
  }, [setupNeeded.data, navigate]);

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

          <form onSubmit={handleSubmit}>
            <TextField label="Användarnamn" fullWidth required value={username} autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} autoFocus />
            <TextField label="Lösenord" fullWidth required type="password" value={password} autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} sx={{ mb: 3 }} />
            <Button type="submit" variant="contained" fullWidth size="large"
              disabled={loginMutation.isPending || !username || !password}>
              {loginMutation.isPending ? "Loggar in…" : "Logga in"}
            </Button>
          </form>
          {setupNeeded.data && (
            <Typography variant="body2" sx={{ mt: 2 }}>
              Inget konto finns ännu – <Link component={RouterLink} to="/setup">skapa det första</Link>.
            </Typography>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
