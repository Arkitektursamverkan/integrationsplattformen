import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "./client";

export interface Schedule {
  id: string;
  flow_id: string;
  cron_expression: string;
  timezone: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCreate {
  flow_id: string;
  cron_expression: string;
  timezone?: string;
  enabled?: boolean;
}

export interface ScheduleUpdate {
  cron_expression?: string;
  timezone?: string;
  enabled?: boolean;
}

export function useSchedules() {
  return useQuery({
    queryKey: ["schedules"],
    queryFn: async () => {
      const { data } = await client.get<Schedule[]>("/schedules");
      return data;
    },
  });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ScheduleCreate) => {
      const { data } = await client.post<Schedule>("/schedules", body);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: ScheduleUpdate & { id: string }) => {
      const { data } = await client.put<Schedule>(`/schedules/${id}`, body);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await client.delete(`/schedules/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}
