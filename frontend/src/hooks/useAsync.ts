import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  reload: () => void;
}

/** 只处理「最后一次请求」的结果，避免切换筛选时旧响应覆盖新数据。 */
export function useAsync<T>(factory: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const seqRef = useRef(0);
  const factoryRef = useRef(factory);
  factoryRef.current = factory;

  useEffect(() => {
    const seq = ++seqRef.current;
    let alive = true;
    setLoading(true);
    factoryRef
      .current()
      .then((result) => {
        if (!alive || seq !== seqRef.current) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!alive || seq !== seqRef.current) return;
        setError(err);
      })
      .finally(() => {
        if (!alive || seq !== seqRef.current) return;
        setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { data, loading, error, reload };
}
