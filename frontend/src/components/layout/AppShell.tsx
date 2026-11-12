import { useSyncExternalStore } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { authStore } from '../../stores/authStore';
import { uiStore } from '../../stores/uiStore';
import { NAV_ITEMS } from '../../constants/ui';
import { ROLE_LABELS, can } from '../../constants/roles';
import { useAsync } from '../../hooks/useAsync';
import { overviewApi } from '../../api/overview';
import { dateText } from '../../utils/format';
import Toasts from '../common/Toasts';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const navigate = useNavigate();
  const role = state.user?.role;
  const navItems = NAV_ITEMS.filter((item) => can(role, item.permission));
  const { data: overview } = useAsync(() => overviewApi.get(), []);

  function logout() {
    authStore.logout();
    uiStore.push('已退出，记录板回到待登录状态');
    navigate('/login', { replace: true });
  }

  const latest = overview?.latest_run;
  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-mark">
          <b>rentlens</b>
          <small>看板 NO.03</small>
        </div>
        <div className="rail-clip" />
        <nav className="rail-nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              <i>{item.no}</i>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="rail-vertical">安家数据 · 带看记录板 · 2026-W46</div>
        <div className="rail-foot">
          安家数据服务
          <br />
          楼盘研究组 · 8 人 · 3 家中介
          <br />
          <span className="mono">{role ? ROLE_LABELS[role] : '未登录'}</span>
          <br />
          <span className="mono" data-testid="worker-state">
            采集器 {overview ? (overview.worker_alive ? '在岗' : '心跳超时') : '…'}
          </span>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div>
            <div className="eyebrow">SECOND-HAND LISTING DESK · 二手房挂牌核验</div>
            <h1>二手房挂牌采集与虚高报价核验台</h1>
            <div className="sub">
              {latest
                ? `最近一次采集 ${dateText(latest.started_at)} · ${latest.items_fetched} 条 / 限流 ${latest.throttled_count} 次 · ${latest.dedup_count} 套去重后口径`
                : '还没有采集记录，先去「采集源与运行」跑一次'}
            </div>
          </div>
          <div className="topbar-meta">
            <div className="who">
              <b>{state.user?.display_name}</b>
              <div className="tiny muted">{state.user?.email}</div>
            </div>
            <button className="btn btn-sm" onClick={logout}>
              退出
            </button>
          </div>
        </div>
        {children}
      </div>
      <Toasts />
    </div>
  );
}
