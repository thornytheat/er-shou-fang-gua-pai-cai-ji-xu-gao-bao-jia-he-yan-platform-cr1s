import { useSyncExternalStore } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { authStore } from '../stores/authStore';
import { ROLE_LABELS, can } from '../constants/roles';
import type { Role } from '../types/models';

export function useAuth() {
  return useSyncExternalStore(authStore.subscribe, authStore.getState);
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const state = useAuth();
  const location = useLocation();
  if (!state.bootstrapped) {
    return <div className="main">正在恢复登录态 …</div>;
  }
  if (!state.token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: React.ReactNode;
}) {
  const state = useAuth();
  if (!state.user || !can(state.user.role, permission)) {
    return (
      <div className="forbidden" data-testid="forbidden">
        <div>
          <div className="eyebrow">403 · FORBIDDEN</div>
          <h1>这一栏不在你的记录板上</h1>
          <p className="muted" style={{ fontSize: '0.84rem' }}>
            当前角色「{state.user ? ROLE_LABELS[state.user.role as Role] : '访客'}」没有 {permission} 权限。
            中介客户只能看行情与核验进度；跑采集、复核工单、修单价属于数据专员 / 研究组长。
          </p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
