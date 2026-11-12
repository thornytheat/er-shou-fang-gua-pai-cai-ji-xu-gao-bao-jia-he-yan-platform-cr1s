import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../api/auth';
import { authStore } from '../stores/authStore';
import { errorMessage } from '../utils/errorMessage';
import { DEMO_ACCOUNTS, SCENARIO_NOTES, SOURCE_HIGHLIGHTS } from '../constants/ui';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@rentlens.io');
  const [password, setPassword] = useState('Demo@2026');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await authApi.login(email, password);
      authStore.setSession(result.access_token, result.user);
      navigate(result.user.role === 'client' ? '/listings' : '/listings', { replace: true });
    } catch (err) {
      setError(errorMessage((err as { payload?: unknown }).payload, '登录失败'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <section className="login-wall">
        <div className="eyebrow">ANJIA DATA · RESALE LISTING DESK</div>
        <h1>
          同一套房
          <br />
          在三个平台<em>挂三个价</em>
        </h1>
        <p className="tagline">
          安家数据服务 · 楼盘研究组（8 人）给 3 家本地中介做挂牌行情与外呼名单。每天 08:30 从 5 个平台抓挂牌，
          研究助理抄进 Excel 再人工挑重复、拍脑袋算均价。这一版把「采集 → 去重 → 稳健 z → 复核 → 导报」摆到一块记录板上。
        </p>

        <div className="login-notes">
          {SCENARIO_NOTES.map((note) => (
            <div className="login-note" key={note.v}>
              <b>{note.k}</b>
              <div style={{ fontWeight: 600 }}>{note.v}</div>
              <span>{note.d}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            五个平台 · 各自的口径
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
            {SOURCE_HIGHLIGHTS.map((line) => (
              <li key={line} style={{ marginBottom: 3 }}>
                {line}
              </li>
            ))}
          </ul>
        </div>
        <div className="annot">研究组手写批注：虚高价会把这些均价整体抬上去，先看核验队列再发周报。</div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="eyebrow">值班登录</div>
          <h2>进店 · 带看记录板</h2>
          <p className="sub">挂牌池、房源详情、采集运行与核验队列都在这一块板子上处理。</p>

          <label className="field" style={{ marginBottom: 12 }}>
            <span>邮箱</span>
            <input
              className="input"
              type="email"
              value={email}
              autoComplete="username"
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="field" style={{ marginBottom: 16 }}>
            <span>密码</span>
            <input
              className="input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={busy}>
            {busy ? '核对门牌 …' : '进门'}
          </button>
          {error ? <div className="form-error" style={{ marginTop: 10 }}>{error}</div> : null}

          <div className="quick-accounts">
            演示账号（密码统一 Demo@2026）：
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => {
                  setEmail(account.email);
                  setPassword('Demo@2026');
                }}
              >
                {account.who} · {account.label} · {account.email}
              </button>
            ))}
          </div>
        </form>
        <div className="tiny muted">
          权限差异在服务端生效：中介客户（client）调用运行采集 / 复核工单 / 导出接口会真实返回 403，
          不是前端把按钮藏起来。
        </div>
      </section>
    </div>
  );
}
