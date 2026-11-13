import { http } from './client';
import type { IngestRun, SourceBatch } from '../types/models';

export const ingestApi = {
  list: (limit = 20) => http.get<{ items: IngestRun[] }>(`/ingest-runs?limit=${limit}`),
  detail: (runId: number) => http.get<IngestRun>(`/ingest-runs/${runId}`),
  batches: (runId: number) =>
    http.get<{ run_id: number; items: SourceBatch[] }>(`/ingest-runs/${runId}/batches`),
  run: (sourceIds?: number[]) => http.post<IngestRun>('/ingest-runs', { source_ids: sourceIds || null }),
};
