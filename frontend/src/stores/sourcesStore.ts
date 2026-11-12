/** 采集源 + 运行记录缓存。 */
import type { IngestRun, SourceRow } from '../types/models';
import { sourcesApi } from '../api/sources';
import { ingestApi } from '../api/ingest';

type Listener = () => void;

class SourcesStore {
  private sources: SourceRow[] = [];
  private runs: IngestRun[] = [];
  private loadedAt = 0;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSources = (): SourceRow[] => this.sources;

  getRuns = (): IngestRun[] => this.runs;

  getLatest = (): IngestRun | null => this.runs[0] || null;

  private emit() {
    this.listeners.forEach((listener) => listener());
  }

  async load(force = false): Promise<void> {
    const stale = Date.now() - this.loadedAt > 30_000;
    if (!force && this.sources.length && !stale) return;
    const [sources, runs] = await Promise.all([sourcesApi.list(), ingestApi.list(12)]);
    this.sources = sources.items;
    this.runs = runs.items;
    this.loadedAt = Date.now();
    this.emit();
  }

  async patchSource(sourceId: number, payload: Record<string, unknown>): Promise<SourceRow> {
    const updated = await sourcesApi.patch(sourceId, payload);
    this.sources = this.sources.map((source) => (source.id === sourceId ? { ...source, ...updated } : source));
    this.emit();
    return updated;
  }

  async prependRun(run: IngestRun) {
    this.runs = [run, ...this.runs].slice(0, 12);
    this.loadedAt = 0;
    this.emit();
    await this.load(true);
  }

  invalidate() {
    this.loadedAt = 0;
  }
}

export const sourcesStore = new SourcesStore();
