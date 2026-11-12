import { http } from './client';
import type { IngestRun, SourceRow } from '../types/models';

export const sourcesApi = {
  list: () => http.get<{ items: SourceRow[] }>('/sources'),
  create: (payload: {
    code: string;
    name: string;
    platform: string;
    base_url: string;
    frequency: string;
    rate_limit_per_min: number;
    page_size: number;
    note?: string;
  }) => http.post<SourceRow>('/sources', payload),
  patch: (sourceId: number, payload: Record<string, unknown>) =>
    http.patch<SourceRow>(`/sources/${sourceId}`, payload),
  runOne: (sourceId: number) => http.post<IngestRun>(`/sources/${sourceId}/run`),
};
