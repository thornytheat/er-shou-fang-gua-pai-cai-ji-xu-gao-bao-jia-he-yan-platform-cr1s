import { http, query } from './client';
import type { FlagCounts, FlagPage, PriceFlagRow } from '../types/models';

export const flagsApi = {
  list: (params: { flag_type?: string; review_status?: string; limit?: number }) =>
    http.get<FlagPage>(`/flags${query(params)}`),
  summary: () => http.get<FlagCounts>('/flags/summary'),
  review: (flagId: number, reviewStatus: string, note: string) =>
    http.patch<PriceFlagRow>(`/flags/${flagId}`, { review_status: reviewStatus, note }),
  detect: () => http.post<{ result: Record<string, unknown>; counts: FlagCounts }>('/flags/detect'),
};
