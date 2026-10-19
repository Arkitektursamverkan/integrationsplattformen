import { useQuery } from "@tanstack/react-query";
import client from "./client";

export interface ExecutionLog {
  id: string;
  flow_id: string;
  trigger_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  records_processed: number;
  records_created: number;
  records_updated: number;
  error_message: string | null;
  details: Record<string, unknown> | null;
}

export interface ExecutionLogList {
  executions: ExecutionLog[];
  total: number;
  page: number;
  page_size: number;
}

export function useExecutions(params?: { flow_id?: string; status?: string; page?: number }) {
  return useQuery<ExecutionLogList>({
    queryKey: ["executions", params],
    queryFn: () => client.get("/executions", { params }).then((r) => r.data),
    refetchInterval: 5000,
  });
}
