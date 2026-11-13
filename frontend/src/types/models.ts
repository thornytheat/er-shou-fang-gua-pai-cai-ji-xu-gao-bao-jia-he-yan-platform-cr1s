export type Role = 'admin' | 'analyst' | 'client';

export interface UserInfo {
  id: number;
  email: string;
  display_name: string;
  role: Role;
  role_label: string;
  permissions: string[];
}

export interface SourceBatch {
  id: number;
  run_id: number;
  source_id: number;
  source_code: string;
  status: 'replaced' | 'unchanged' | 'isolated';
  pages_expected: number;
  pages_fetched: number;
  received_count: number;
  isolated_count: number;
  replaced_count: number;
  created_count: number;
  updated_count: number;
  deleted_count: number;
  throttled_count: number;
  backoff_ms: number;
  content_hash: string | null;
  reason: string | null;
  detail: Record<string, unknown>;
  created_at: string | null;
}

export interface SourceRow {
  id: number;
  code: string;
  name: string;
  platform: string;
  platform_label: string;
  base_url: string;
  frequency: string;
  rate_limit_per_min: number;
  page_size: number;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_items: number;
  listing_count: number;
  note: string | null;
  latest_batch?: SourceBatch | null;
}

export interface IngestRun {
  id: number;
  run_no: string;
  trigger: string;
  trigger_label: string;
  status: string;
  status_label: string;
  sources_total: number;
  pages_fetched: number;
  items_fetched: number;
  throttled_count: number;
  backoff_ms: number;
  created_count: number;
  updated_count: number;
  cluster_count: number;
  duplicate_count: number;
  dedup_count: number;
  flag_count: number;
  duration_ms: number;
  operator_email: string;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  summary: {
    throttle_log?: { source: string; page: number; status: number; wait_ms: number }[];
    flag_counts?: Record<string, number>;
    blocks?: BlockPriceLine[];
    unknown_area?: number;
    edge_count?: number;
    pair_count?: number;
    recomputed?: boolean;
    replaced_total?: number;
    isolated_total?: number;
    deleted_total?: number;
    source_batches?: SourceBatch[];
  };
}

export interface BlockPriceLine {
  community: string;
  layout: string;
  primary_count: number;
  all_count: number;
  naive_mean: number | null;
  dedup_mean: number | null;
  median_price?: number | null;
  mad?: number | null;
  unknown_count?: number;
  inflation_pct?: number | null;
}

export interface ListingRow {
  id: number;
  source_id: number;
  source_name: string;
  source_platform: string;
  source_listing_no: string;
  community: string;
  layout: string;
  area_sqm: number | null;
  floor: number | null;
  total_floors: number | null;
  floor_band: string | null;
  unit_price: number | null;
  total_price_wan: number | null;
  list_date: string | null;
  title: string;
  agent_name: string | null;
  agent_contact: string | null;
  completeness: number;
  cluster_id: number | null;
  cluster_size: number;
  platform_count: number;
  is_primary: boolean;
  quarantined: boolean;
  flag_type: string | null;
  flag_label: string | null;
  deviation_pct: number | null;
  review_status: string | null;
}

export interface ListingPage {
  items: ListingRow[];
  total: number;
  page: number;
  page_size: number;
  sums: {
    page_avg_unit_price?: number | null;
    page_min_unit_price?: number | null;
    page_max_unit_price?: number | null;
    unknown_area?: number;
    duplicate_rows?: number;
    quarantined_rows?: number;
  };
}

export interface ListingMember {
  id: number;
  source_name: string;
  source_platform: string;
  source_listing_no: string;
  unit_price: number | null;
  total_price_wan: number | null;
  list_date: string | null;
  title: string;
  floor: number | null;
  floor_band: string | null;
  similarity: number | null;
  is_primary: boolean;
}

export interface PriceSeriesPoint {
  date: string | null;
  unit_price: number | null;
  source_name: string;
  label: string;
  is_primary: boolean;
}

export interface ListingDetail {
  listing: ListingRow;
  members: ListingMember[];
  block: BlockPriceLine & {
    block_key?: string;
    all_count?: number;
    primary_count?: number;
    min_price?: number | null;
    max_price?: number | null;
    updated_at?: string | null;
  };
  flag: {
    id: number;
    flag_type: string;
    flag_label: string;
    unit_price: number;
    median_price: number;
    deviation_pct: number;
    z_score: number | null;
    confidence: number;
    sample_size: number;
    review_status: string;
    review_label: string;
    review_note: string | null;
    reviewed_by: string | null;
    reviewed_at: string | null;
  } | null;
  price_series: PriceSeriesPoint[];
}

export interface PriceFlagRow {
  id: number;
  listing_id: number;
  cluster_id: number | null;
  flag_type: string;
  flag_label: string;
  community: string;
  layout: string;
  unit_price: number;
  median_price: number;
  deviation_pct: number;
  z_score: number | null;
  confidence: number;
  sample_size: number;
  review_status: string;
  review_label: string;
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  detected_at: string | null;
  title: string | null;
  area_sqm: number | null;
  list_date: string | null;
  source_name: string | null;
}

export interface FlagPage {
  items: PriceFlagRow[];
  total: number;
  counts: FlagCounts;
}

export interface FlagCounts {
  total: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
}

export interface Overview {
  sources: number;
  sources_enabled: number;
  listings: number;
  quarantined: number;
  primaries: number;
  duplicate_clusters: number;
  duplicate_members: number;
  flags: FlagCounts;
  blocks: BlockPriceLine[];
  latest_run: IngestRun | null;
  worker_alive: boolean;
  server_time: string;
}

export interface ClusterRow {
  id: number;
  community: string;
  layout: string;
  block_key: string;
  primary_listing_id: number;
  member_count: number;
  platform_count: number;
  avg_unit_price: number | null;
  min_similarity: number | null;
  max_similarity: number | null;
  spread_pct: number | null;
  primary_title: string | null;
  primary_list_date: string | null;
}

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  detail?: unknown;
}
