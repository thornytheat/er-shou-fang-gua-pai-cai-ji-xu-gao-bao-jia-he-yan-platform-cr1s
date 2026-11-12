/** 挂牌池筛选状态 + 最近一页缓存（详情页返回时保留筛选）。 */
import type { ListingPage } from '../types/models';
import { PAGE_SIZE } from '../constants/ui';

export interface ListingFilterState {
  q: string;
  community: string;
  layout: string;
  sourceId: number | '';
  flagType: string;
  duplicateOnly: boolean;
  primaryOnly: boolean;
  sort: string;
  order: string;
  page: number;
  pageSize: number;
}

type Listener = () => void;

const INITIAL: ListingFilterState = {
  q: '',
  community: '',
  layout: '',
  sourceId: '',
  flagType: '',
  duplicateOnly: false,
  primaryOnly: false,
  sort: 'unit_price',
  order: 'desc',
  page: 1,
  pageSize: PAGE_SIZE,
};

class ListingsStore {
  private state: ListingFilterState = { ...INITIAL };
  private cache: ListingPage | null = null;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getState = (): ListingFilterState => this.state;

  getCache = (): ListingPage | null => this.cache;

  private emit() {
    this.listeners.forEach((listener) => listener());
  }

  patch(next: Partial<ListingFilterState>) {
    const resetsPage = Object.keys(next).some((key) => key !== 'page');
    this.state = { ...this.state, ...next, ...(resetsPage && next.page === undefined ? { page: 1 } : {}) };
    this.emit();
  }

  reset() {
    this.state = { ...INITIAL };
    this.cache = null;
    this.emit();
  }

  setCache(page: ListingPage | null) {
    this.cache = page;
  }
}

export const listingsStore = new ListingsStore();
