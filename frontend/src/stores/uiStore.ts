/** 轻量 toast 队列。 */
export interface Toast {
  id: number;
  kind: 'info' | 'ok' | 'error';
  text: string;
}

type Listener = () => void;

class UiStore {
  private toasts: Toast[] = [];
  private seq = 0;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getToasts = (): Toast[] => this.toasts;

  private emit() {
    this.listeners.forEach((listener) => listener());
  }

  push(text: string, kind: Toast['kind'] = 'info') {
    const toast: Toast = { id: ++this.seq, kind, text };
    this.toasts = [...this.toasts, toast].slice(-4);
    this.emit();
    window.setTimeout(() => this.dismiss(toast.id), 4200);
  }

  dismiss(id: number) {
    this.toasts = this.toasts.filter((toast) => toast.id !== id);
    this.emit();
  }

  ok(text: string) {
    this.push(text, 'ok');
  }

  error(text: string) {
    this.push(text, 'error');
  }
}

export const uiStore = new UiStore();
