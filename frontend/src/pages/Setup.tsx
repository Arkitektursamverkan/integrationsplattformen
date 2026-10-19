import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Button, Card, CardContent, TextField, Typography, Alert } from "@mui/material";
import { useSetup, setTokens } from "@/api/auth";

export default function Setup() {
  const navigate = useNavigate();
  const setupMutation = useSetup();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    try {
      const tokens = await setupMutation.mutateAsync({ username, password, full_name: fullName || undefined, email: email || undefined });
      setTokens(tokens);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Setup failed");
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "grey.100" }}>
      <Card sx={{ maxWidth: 450, width: "100%" }}>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>Welcome</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Create the first admin account to get started with the Integration Platform.
          </Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <TextField label="Username" fullWidth required value={username}
              onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} autoFocus />
            <TextField label="Full Name (optional)" fullWidth value={fullName}
              onChange={(e) => setFullName(e.target.value)} sx={{ mb: 2 }} />
            <TextField label="Email (optional)" fullWidth type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} sx={{ mb: 2 }} />
            <TextField label="Password" fullWidth required type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} sx={{ mb: 2 }}
              helperText="Minimum 8 characters" />
            <TextField label="Confirm Password" fullWidth required type="password" value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)} sx={{ mb: 3 }} />
            <Button type="submit" variant="contained" fullWidth size="large"
              disabled={setupMutation.isPending || !username || !password || !confirmPassword}>
              {setupMutation.isPending ? "Creating account..." : "Create Admin Account"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
