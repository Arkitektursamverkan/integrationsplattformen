import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, Link, TextField, Typography, Alert } from "@mui/material";
import { useSetup, useSetupNeeded, setTokens } from "@/api/auth";

export default function Setup() {
  const navigate = useNavigate();
  const setupMutation = useSetup();
  const setupNeeded = useSetupNeeded();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  // Once an account exists this page can do nothing: log in instead.
  useEffect(() => {
    if (setupNeeded.data === false) navigate("/login", { replace: true });
  }, [setupNeeded.data, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Lösenorden är inte lika");
      return;
    }
    if (password.length < 8) {
      setError("Lösenordet måste ha minst 8 tecken");
      return;
    }
    try {
      const tokens = await setupMutation.mutateAsync({ username, password, full_name: fullName || undefined, email: email || undefined });
      setTokens(tokens);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.status === 400 ? "Det finns redan ett konto – logga in i stället." : "Kontot kunde inte skapas");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "grey.100" }}>
      <Card sx={{ maxWidth: 450, width: "100%" }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>Välkommen</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 3 }}>
            Skapa det första administratörskontot i Integrationsplattformen. Du loggar sedan in med användarnamnet.
          </Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField label="Användarnamn" fullWidth required value={username} autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} autoFocus />
            <TextField label="Namn (valfritt)" fullWidth value={fullName}
              onChange={(e) => setFullName(e.target.value)} sx={{ mb: 2 }} />
            <TextField label="E-post (valfritt)" fullWidth type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} sx={{ mb: 2 }} />
            <TextField label="Lösenord" fullWidth required type="password" value={password} autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)} sx={{ mb: 2 }}
              helperText="Minst 8 tecken" />
            <TextField label="Upprepa lösenordet" fullWidth required type="password" value={confirmPassword} autoComplete="new-password"
              onChange={(e) => setConfirmPassword(e.target.value)} sx={{ mb: 3 }} />
            <Button type="submit" variant="contained" fullWidth size="large"
              disabled={setupMutation.isPending || !username || !password || !confirmPassword}>
              {setupMutation.isPending ? "Skapar kontot…" : "Skapa administratörskontot"}
            </Button>
          </form>
          <Typography variant="body2" sx={{ mt: 2 }}>
            Har du redan ett konto? <Link component={RouterLink} to="/login">Logga in</Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
