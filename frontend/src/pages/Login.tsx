import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, TextField, Typography, Alert } from "@mui/material";
import { useLogin, setTokens } from "@/api/auth";

export default function Login() {
  const navigate = useNavigate();
  const loginMutation = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const tokens = await loginMutation.mutateAsync({ username, password });
      setTokens(tokens);
      navigate("/");
    } catch {
      setError("Invalid username or password");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "grey.100" }}>
      <Card sx={{ maxWidth: 400, width: "100%" }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>Integration Platform</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>Sign in to manage your integrations</Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField label="Username" fullWidth required value={username}
              onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} autoFocus />
            <TextField label="Password" fullWidth required type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} sx={{ mb: 3 }} />
            <Button type="submit" variant="contained" fullWidth size="large"
              disabled={loginMutation.isPending || !username || !password}>
              {loginMutation.isPending ? "Signing in..." : "Sign In"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
