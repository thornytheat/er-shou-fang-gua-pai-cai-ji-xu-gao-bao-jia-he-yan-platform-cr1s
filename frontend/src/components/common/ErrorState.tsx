import { errorMessage, statusHint } from '../../utils/errorMessage';
import type { ApiError } from '../../api/client';

export default function ErrorState({
  error,
  onRetry,
  title = '这一步没跑通',
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const status = (error as ApiError | undefined)?.status;
  const payload = (error as ApiError | undefined)?.payload;
  return (
    <div className="error-state" data-testid="error-state">
      <strong>{title}</strong>
      <div>{errorMessage(payload, '网络或服务暂时不可用')}</div>
      <div className="tiny muted" style={{ marginTop: 4 }}>
        {statusHint(status)}
      </div>
      {onRetry ? (
        <div style={{ marginTop: 10 }}>
          <button className="btn btn-sm" onClick={onRetry} data-testid="error-retry">
            重试
          </button>
        </div>
      ) : null}
    </div>
  );
}
