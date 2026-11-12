import { http } from './client';
import type { ClusterRow } from '../types/models';

export interface RecomputeResult {
  result: {
    cluster_count: number;
    duplicate_count: number;
    dedup_count: number;
    member_total: number;
    edge_count: number;
    pair_count: number;
    flag_counts: Record<string, number>;
    flag_total: number;
    blocks: number;
  };
  pending_reviews: number;
}

export const clustersApi = {
  list: (duplicateOnly = true, limit = 60) =>
    http.get<{ items: ClusterRow[]; total: number; duplicate_total: number; dedup_total: number }>(
      `/clusters?duplicate_only=${duplicateOnly}&limit=${limit}`,
    ),
  recompute: () => http.post<RecomputeResult>('/clusters/recompute'),
};
