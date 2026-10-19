import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "./client";

export interface FlowStep {
  id: string;
  flow_id: string;
  step_order: number;
  step_type: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Flow {
  id: string;
  name: string;
  description: string | null;
  connection_id: string;
  enabled: boolean;
  flow_definition: Record<string, unknown> | null;
  post_exec_webhook_url: string | null;
  steps?: FlowStep[];
  created_at: string;
  updated_at: string;
}

export interface FlowStepCreate {
  step_order: number;
  step_type: string;
  config: Record<string, unknown>;
}

export interface FlowCreate {
  name: string;
  description?: string;
  connection_id: string;
  enabled?: boolean;
  flow_definition?: Record<string, unknown>;
  steps?: FlowStepCreate[];
}

export function useFlows() {
  return useQuery<Flow[]>({
    queryKey: ["flows"],
    queryFn: () => client.get("/flows").then((r) => r.data),
  });
}

export function useFlow(id: string) {
  return useQuery<Flow>({
    queryKey: ["flows", id],
    queryFn: () => client.get(`/flows/${id}`).then((r) => r.data),
    enabled: !!id,
  });
}

export function useCreateFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: FlowCreate) => client.post("/flows", data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["flows"] }),
  });
}

export interface FlowUpdateArgs {
  flow_id: string;
  name?: string;
  description?: string;
  enabled?: boolean;
  post_exec_webhook_url?: string | null;
  steps?: FlowStepCreate[];
}

export function useUpdateFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ flow_id, ...data }: FlowUpdateArgs) => client.put(`/flows/${flow_id}`, data).then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["flows", vars.flow_id] });
    },
  });
}

export function useDeleteFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.delete(`/flows/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["flows"] }),
  });
}

export function useExecuteFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.post(`/flows/${id}/execute`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["executions"] });
      qc.invalidateQueries({ queryKey: ["flows"] });
    },
  });
}
