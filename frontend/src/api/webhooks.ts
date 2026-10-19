import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";

export interface Webhook {
  id: string;
  flow_id: string;
  path_token: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookCreate {
  flow_id: string;
  secret?: string;
  enabled?: boolean;
}

export function useWebhooks() {
  return useQuery({
    queryKey: ["webhooks"],
    queryFn: async () => {
      const { data } = await client.get<Webhook[]>("/webhooks");
      return data;
    },
  });
}

export function useCreateWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: WebhookCreate) => {
      const { data } = await client.post<Webhook>("/webhooks", body);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }),
  });
}

export function useDeleteWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await client.delete(`/webhooks/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }),
  });
}
