import { useToasts } from '../../hooks/useToast';
import { uiStore } from '../../stores/uiStore';

export default function Toasts() {
  const toasts = useToasts();
  if (!toasts.length) return null;
  return (
    <div className="toasts" data-testid="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.kind}`} onClick={() => uiStore.dismiss(toast.id)}>
          {toast.text}
        </div>
      ))}
    </div>
  );
}
