/** 去重簇缓存：房源详情页按需拉取，避免重复请求。 */
import type { ClusterRow } from '../types/models';
import { clustersApi } from '../api/clusters';

type Listener = () => void;

class ClustersStore {
  private items: ClusterRow[] = [];
  private loadedAt = 0;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getItems = (): ClusterRow[] => this.items;

  private emit() {
    this.listeners.forEach((listener) => listener());
  }

  async ensure(force = false): Promise<ClusterRow[]> {
    const stale = Date.now() - this.loadedAt > 60_000;
    if (!force && this.items.length && !stale) return this.items;
    const result = await clustersApi.list(true, 60);
    this.items = result.items;
    this.loadedAt = Date.now();
    this.emit();
    return this.items;
  }

  invalidate() {
    this.loadedAt = 0;
  }
}

export const clustersStore = new ClustersStore();
