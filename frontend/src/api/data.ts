import { useQuery } from "@tanstack/react-query";
import client from "./client";

export interface DataRecord {
  id: string;
  flow_id: string;
  source_type: string;
  external_id: string;
  data: Record<string, unknown>;
  checksum: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DataRecordList {
  records: DataRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface DataSourceSummary {
  flow_id: string;
  flow_name: string;
  connector_type: string;
  record_count: number;
  last_sync: string | null;
  status: string;
}

export function useDataSources() {
  return useQuery<DataSourceSummary[]>({
    queryKey: ["data-sources"],
    queryFn: () => client.get("/data/sources").then((r) => r.data),
  });
}

export function useDataRecords(flowId: string, page = 1, pageSize = 100) {
  return useQuery<DataRecordList>({
    queryKey: ["data-records", flowId, page, pageSize],
    queryFn: () => client.get(`/data/${flowId}/records`, { params: { page, page_size: pageSize } }).then((r) => r.data),
    enabled: !!flowId,
  });
}
