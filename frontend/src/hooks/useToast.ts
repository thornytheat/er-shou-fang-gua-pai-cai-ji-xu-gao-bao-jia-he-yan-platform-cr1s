import { useSyncExternalStore } from 'react';
import { uiStore } from '../stores/uiStore';

export function useToasts() {
  return useSyncExternalStore(uiStore.subscribe, uiStore.getToasts);
}

export function useToast() {
  return {
    ok: (text: string) => uiStore.ok(text),
    error: (text: string) => uiStore.error(text),
    info: (text: string) => uiStore.push(text, 'info'),
  };
}
