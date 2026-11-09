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

export function setTokens(tokens: TokenResponse) {
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
  localStorage.setItem("user_role", tokens.role);
  localStorage.setItem("username", tokens.username);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user_role");
  localStorage.removeItem("username");
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
    mutationFn: (data: { username: string; password: string; full_name?: string; email?: string }) =>
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

/** Whether no user exists yet, so the first admin must be created at /setup. */
export function useSetupNeeded() {
  return useQuery<boolean>({
    queryKey: ["setup-needed"],
    queryFn: () => client.get("/auth/setup").then((r) => !!r.data?.needed),
    retry: false,
  });
}
