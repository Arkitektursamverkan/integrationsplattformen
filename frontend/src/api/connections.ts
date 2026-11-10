import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";

export interface Connection {
  id: string;
  name: string;
  connector_type: string;
  description: string | null;
  config: Record<string, unknown>;
  auth_type: string;
  status: string;
  last_tested_at: string | null;
  created_at: string;
  updated_at: string;
  // Whether credentials are stored (they are never returned).
  has_credentials?: boolean;
  // Only in the reply to an update: the address's host or the TLS check
  // changed, so the stored credentials were removed and must be entered again.
  credentials_cleared?: boolean;
}

export interface ConnectionCreate {
  name: string;
  connector_type: string;
  description?: string;
  config?: Record<string, unknown>;
  credentials?: Record<string, unknown>;
  auth_type?: string;
}

export function useConnections() {
  return useQuery<Connection[]>({
    queryKey: ["connections"],
    queryFn: () => client.get("/connections").then((r) => r.data),
  });
}

export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ConnectionCreate) => client.post("/connections", data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });
}

export interface ConnectionUpdate {
  name?: string;
  description?: string;
  config?: Record<string, unknown>;
  credentials?: Record<string, unknown>;
  auth_type?: string;
  status?: string;
}

export function useUpdateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConnectionUpdate }) =>
      client.put(`/connections/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });
}

export function useDeleteConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.delete(`/connections/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: (id: string) => client.post(`/connections/${id}/test`).then((r) => r.data),
  });
}

export function useConnectorTypes() {
  return useQuery<{ connector_types: string[] }>({
    queryKey: ["connector-types"],
    queryFn: () => client.get("/connections/types").then((r) => r.data),
  });
}
