import { useCallback, useEffect, useState } from 'react';

/** 通用筛选状态：patch 局部更新，reset 回到初始值。 */
export function useFilters<T extends Record<string, unknown>>(initial: T) {
  const [state, setState] = useState<T>(initial);
  const patch = useCallback((next: Partial<T>) => {
    setState((current) => ({ ...current, ...next }));
  }, []);
  const reset = useCallback(() => setState(initial), [initial]);
  return { filters: state, patch, reset };
}

/** 输入框防抖：搜索框每次按键都请求会打满限流额度。 */
export function useDebouncedValue<T>(value: T, delay = 320): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
