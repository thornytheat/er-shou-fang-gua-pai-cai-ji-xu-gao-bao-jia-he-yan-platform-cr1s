/** 核验队列：筛选、计数、复核后的本地乐观更新。 */
import type { FlagCounts, PriceFlagRow } from '../types/models';
import { flagsApi } from '../api/flags';

export interface FlagFilterState {
  flagType: string;
  reviewStatus: string;
}

type Listener = () => void;

class FlagsStore {
  private state: FlagFilterState = { flagType: '', reviewStatus: '' };
  private items: PriceFlagRow[] = [];
  private counts: FlagCounts | null = null;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getState = (): FlagFilterState => this.state;

  getItems = (): PriceFlagRow[] => this.items;

  getCounts = (): FlagCounts | null => this.counts;

  private emit() {
    this.listeners.forEach((listener) => listener());
  }

  patch(next: Partial<FlagFilterState>) {
    this.state = { ...this.state, ...next };
    this.emit();
  }

  async load(): Promise<{ items: PriceFlagRow[]; counts: FlagCounts }> {
    const result = await flagsApi.list({
      flag_type: this.state.flagType || undefined,
      review_status: this.state.reviewStatus || undefined,
      limit: 80,
    });
    this.items = result.items;
    this.counts = result.counts;
    this.emit();
    return { items: result.items, counts: result.counts };
  }

  applyReview(updated: PriceFlagRow) {
    this.items = this.items.map((item) => (item.id === updated.id ? { ...item, ...updated } : item));
    this.emit();
  }

  setCounts(counts: FlagCounts) {
    this.counts = counts;
    this.emit();
  }
}

export const flagsStore = new FlagsStore();
