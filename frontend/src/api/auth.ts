import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: string;
  username: string;
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

// Uppdateringstoken gäller i sju dagar: den ligger i sessionStorage (som i
// portalen), så att den försvinner när fliken stängs och inte delas mellan
// flikar. Åtkomsttoken (en timme) ligger kvar i localStorage.
export function setTokens(tokens: TokenResponse) {
  localStorage.setItem("access_token", tokens.access_token);
  sessionStorage.setItem("refresh_token", tokens.refresh_token);
  // Från versioner som sparade den i localStorage.
  localStorage.removeItem("refresh_token");
  localStorage.setItem("user_role", tokens.role);
  localStorage.setItem("username", tokens.username);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  sessionStorage.removeItem("refresh_token");
  localStorage.removeItem("user_role");
  localStorage.removeItem("username");
}

// En uppdateringstoken som en tidigare version lämnat i localStorage tas bort.
try {
  localStorage.removeItem("refresh_token");
} catch {
  /* lagringen kan vara avstängd */
}

export function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

export function isLoggedIn(): boolean {
  return !!localStorage.getItem("access_token");
}

export function useLogin() {
  return useMutation({
    mutationFn: (data: LoginRequest) =>
      client.post("/auth/login", data).then((r) => r.data as TokenResponse),
  });
}

export function useSetup() {
  return useMutation({
    mutationFn: (data: { username: string; password: string; full_name?: string; email?: string; setup_code?: string }) =>
      client.post("/auth/setup", data).then((r) => r.data as TokenResponse),
  });
}

export function useMe() {
  return useQuery<User>({
    queryKey: ["me"],
    queryFn: () => client.get("/auth/me").then((r) => r.data),
    enabled: isLoggedIn(),
    retry: false,
  });
}

export interface SetupStatus {
  /** No user exists yet, so the first admin must be created at /setup. */
  needed: boolean;
  /** Creating it takes the installation's one-time SETUP_CODE. */
  code_required: boolean;
}

export function useSetupStatus() {
  return useQuery<SetupStatus>({
    queryKey: ["setup-needed"],
    queryFn: () => client.get("/auth/setup").then((r) => ({ needed: !!r.data?.needed, code_required: !!r.data?.code_required })),
    retry: false,
  });
}
