import { downloadCsv, http, query } from './client';

export interface ExportPreview {
  headers: string[];
  rows: Record<string, string | number>[];
  total_rows: number;
}

export const exportsApi = {
  preview: (params: { community?: string; since?: string; flag_only?: boolean }) =>
    http.get<ExportPreview>(`/exports/market-preview${query(params)}`),
  download: (params: { community?: string; since?: string; flag_only?: boolean }) =>
    downloadCsv(`/exports/market.csv${query(params)}`, 'rentlens-market.csv'),
};
