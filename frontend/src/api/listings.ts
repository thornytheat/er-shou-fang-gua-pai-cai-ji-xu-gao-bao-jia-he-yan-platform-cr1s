import { http, query } from './client';
import type { ListingDetail, ListingPage, ListingRow } from '../types/models';

export interface ListingFilters {
  q?: string;
  community?: string;
  layout?: string;
  source_id?: number | '';
  flag_type?: string;
  duplicate_only?: boolean;
  primary_only?: boolean;
  sort?: string;
  order?: string;
  page?: number;
  page_size?: number;
}

export const listingsApi = {
  list: (filters: ListingFilters) => http.get<ListingPage>(`/listings${query({ ...filters })}`),
  detail: (listingId: number) => http.get<ListingDetail>(`/listings/${listingId}`),
  options: () =>
    http.get<{
      communities: string[];
      layouts: string[];
      sources: { id: number; name: string; platform: string }[];
      pending_reviews: number;
    }>('/listings/options'),
  fixPrice: (listingId: number, unit_price: number, note: string) =>
    http.patch<ListingDetail>(`/listings/${listingId}/price`, { unit_price, note }),
};

export type { ListingRow };
