import type { ApiErrorPayload } from '../types/models';

const FALLBACK: Record<string, string> = {
  AUTH_INVALID: '邮箱或密码不正确',
  AUTH_MISSING: '登录已过期，请重新登录',
  FORBIDDEN: '当前角色无权执行该操作',
  NOT_FOUND: '对象不存在或已被清理',
  CONFLICT: '对象已存在，换一个编码试试',
  RATE_LIMITED: '请求过于频繁，稍后再试',
  VALIDATION: '请求参数不合法',
  INGEST_RUNNING: '已有采集任务在运行',
  EXPORT_EMPTY: '当前筛选条件下没有可导出的记录',
  INTERNAL: '服务内部错误',
};

export function errorMessage(payload: unknown, fallback = '操作失败'): string {
  const data = payload as ApiErrorPayload | string | null;
  if (typeof data === 'string' && data.trim()) return data;
  if (data && typeof data === 'object') {
    if (data.code && FALLBACK[data.code]) {
      return data.detail && typeof data.detail === 'string'
        ? `${FALLBACK[data.code]}（${data.detail}）`
        : FALLBACK[data.code];
    }
    if (data.message) return String(data.message);
  }
  return fallback;
}

export function statusHint(status: number | undefined): string {
  if (status === 403) return '后端按角色拒绝了这次请求（HTTP 403），不是前端把按钮藏起来。';
  if (status === 401) return '登录态已失效，回到登录页重新进店。';
  if (status === 404) return '数据可能被重新采集覆盖了，刷新列表试试。';
  if (status === 429) return '限流额度用完了，等一分钟再操作。';
  return '可以重试，或者回到列表重新选一条记录。';
}
