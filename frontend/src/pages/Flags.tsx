import { useEffect, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { flagsApi } from '../api/flags';
import { exportsApi } from '../api/exports';
import { useToast } from '../hooks/useToast';
import { authStore } from '../stores/authStore';
import { flagsStore } from '../stores/flagsStore';
import { can } from '../constants/roles';
import { FLAG_TYPE_LABELS, FLAG_TYPE_ORDER, REVIEW_LABELS } from '../constants/enums';
import { confidence, dateText, pct, shortDate, yuan } from '../utils/format';
import { errorMessage } from '../utils/errorMessage';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import LedgerTable from '../components/common/LedgerTable';
import MetricStrip from '../components/common/MetricStrip';
import StampTag from '../components/common/StampTag';
import type { PriceFlagRow } from '../types/models';

const DEFAULT_NOTES: Record<string, string> = {
  high: '已电话核实：业主试探价，按去重后中位价入周报',
  low: '引流价：门店确认本月无此房源，标注不进推荐名单',
  uncertain: '边界样本：样本量够但偏离在 25%~30%，留待下周复核',
};

export default function Flags() {
  const auth = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const filters = useSyncExternalStore(flagsStore.subscribe, flagsStore.getState);
  const items = useSyncExternalStore(flagsStore.subscribe, flagsStore.getItems);
  const counts = useSyncExternalStore(flagsStore.subscribe, flagsStore.getCounts);
  const role = auth.user?.role;
  const canReview = can(role, 'flag:review');
  const canExport = can(role, 'export:read');
  const toast = useToast();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<PriceFlagRow | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [preview, setPreview] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      const result = await flagsStore.load();
      setError(null);
      if (!selected && result.items.length) {
        setSelected(result.items[0]);
        setNote(DEFAULT_NOTES[result.items[0].flag_type] || '');
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [filters.flagType, filters.reviewStatus]);

  useEffect(() => {
    exportsApi
      .preview({})
      .then((data) => setPreview(data.total_rows))
      .catch(() => setPreview(null));
  }, []);

  async function review(flag: PriceFlagRow, status: 'confirmed' | 'dismissed') {
    setBusy(`review-${flag.id}`);
    try {
      const updated = await flagsApi.review(flag.id, status, note || DEFAULT_NOTES[flag.flag_type] || '');
      flagsStore.applyReview(updated);
      toast.ok(status === 'confirmed' ? '工单已确认，进入本周行情口径' : '工单已驳回，保留原始挂牌价');
      setSelected({ ...flag, ...updated });
      await load();
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '复核失败'));
    } finally {
      setBusy('');
    }
  }

  async function detect() {
    setBusy('detect');
    try {
      const result = await flagsApi.detect();
      toast.ok(`核验重跑完成：虚高 ${result.counts.by_type.high} / 虚低 ${result.counts.by_type.low} / 待确认 ${result.counts.by_type.uncertain}`);
      await load();
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '重跑失败'));
    } finally {
      setBusy('');
    }
  }

  async function exportCsv() {
    setBusy('export');
    try {
      const rows = await exportsApi.download({});
      toast.ok(`行情 CSV 已下载，共 ${rows} 行`);
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '导出失败'));
    } finally {
      setBusy('');
    }
  }

  const metrics = [
    { k: '工单总数', v: counts?.total ?? '—', unit: '件', d: '样本 ≥ 8 才判定' },
    { k: '虚高', v: counts?.by_type.high ?? '—', unit: '件', d: '|z|>3 且偏离>30%' },
    { k: '虚低', v: counts?.by_type.low ?? '—', unit: '件', d: '引流价 / 钓鱼价' },
    { k: '待确认', v: counts?.by_type.uncertain ?? '—', unit: '件', d: '偏离落在 25%~30% 边界带' },
    { k: '待复核', v: counts?.by_status.pending ?? '—', unit: '件', d: `已确认 ${counts?.by_status.confirmed ?? 0} / 已驳回 ${counts?.by_status.dismissed ?? 0}` },
    { k: '可导出行数', v: preview ?? '—', unit: '行', d: '去重后主房源口径' },
  ];

  const columns = [
    {
      key: 'flag',
      label: '标记',
      render: (row: PriceFlagRow) => (
        <div className="row" style={{ gap: 5 }}>
          <StampTag kind={row.flag_type} fresh />
          <span className={`stamp ${row.review_status}`}>{REVIEW_LABELS[row.review_status]}</span>
        </div>
      ),
    },
    {
      key: 'house',
      label: '房源',
      render: (row: PriceFlagRow) => (
        <div>
          <div style={{ fontWeight: 600 }}>
            {row.community} · {row.layout}
          </div>
          <div className="tiny muted">
            {row.area_sqm ? `${Math.round(row.area_sqm)}㎡` : '面积缺失'} · 挂牌 {shortDate(row.list_date)}
          </div>
        </div>
      ),
    },
    {
      key: 'deviation',
      label: '偏离中位',
      align: 'right' as const,
      render: (row: PriceFlagRow) => (
        <div>
          <div className="mono" style={{ color: row.deviation_pct > 0 ? 'var(--ochre)' : 'var(--slate)' }}>
            {pct(row.deviation_pct)}
          </div>
          <div className="compare-bar" style={{ width: 92, marginLeft: 'auto', marginTop: 3 }}>
            <i
              style={{
                width: `${Math.min(100, Math.abs(row.deviation_pct) * 2)}%`,
                background: row.deviation_pct > 0 ? 'oklch(0.432 0.118 32)' : 'oklch(0.482 0.034 232)',
                marginLeft: 'auto',
              }}
            />
          </div>
        </div>
      ),
    },
    {
      key: 'z',
      label: '稳健 z',
      align: 'right' as const,
      render: (row: PriceFlagRow) => <span className="mono">{row.z_score !== null ? row.z_score.toFixed(2) : '—'}</span>,
    },
    {
      key: 'price',
      label: '单价 / 中位',
      align: 'right' as const,
      render: (row: PriceFlagRow) => (
        <div>
          <div className="mono">{yuan(row.unit_price)}</div>
          <div className="tiny muted">中位 {yuan(row.median_price)}</div>
        </div>
      ),
    },
    {
      key: 'conf',
      label: '置信度',
      align: 'right' as const,
      render: (row: PriceFlagRow) => (
        <div>
          <div className="mono">{confidence(row.confidence)}</div>
          <div className="tiny muted">样本 {row.sample_size}</div>
        </div>
      ),
    },
    {
      key: 'open',
      label: '',
      align: 'right' as const,
      render: (row: PriceFlagRow) => (
        <button
          className="btn btn-sm btn-ghost"
          onClick={(event) => {
            event.stopPropagation();
            setSelected(row);
            setNote(DEFAULT_NOTES[row.flag_type] || '');
          }}
        >
          核验
        </button>
      ),
    },
  ];

  return (
    <div className="stack fade-in">
      <MetricStrip items={metrics} />

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head">
            <h2>核验队列</h2>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn btn-sm" onClick={detect} disabled={!canReview || busy === 'detect'}>
                {busy === 'detect' ? '重跑…' : '重跑核验'}
              </button>
              <button
                className="btn btn-sm"
                onClick={exportCsv}
                disabled={!canExport || busy === 'export'}
                title={canExport ? '导出行情 CSV' : '中介客户无权导出（服务端 403）'}
                data-testid="export-csv"
              >
                {busy === 'export' ? '导出中…' : '导出行情 CSV'}
              </button>
            </div>
          </div>
          <div className="panel-body stack" style={{ gap: 12 }}>
            <div className="row" style={{ gap: 6 }}>
              {['', ...FLAG_TYPE_ORDER].map((value) => (
                <button
                  key={value || 'all'}
                  className={`btn btn-sm ${filters.flagType === value ? 'btn-primary' : ''}`}
                  onClick={() => flagsStore.patch({ flagType: value })}
                >
                  {value ? `${FLAG_TYPE_LABELS[value]} ${counts?.by_type[value] ?? ''}` : `全部 ${counts?.total ?? ''}`}
                </button>
              ))}
              <span style={{ marginLeft: 'auto' }}>
                <select
                  className="select"
                  value={filters.reviewStatus}
                  onChange={(event) => flagsStore.patch({ reviewStatus: event.target.value })}
                >
                  <option value="">全部状态</option>
                  <option value="pending">待复核</option>
                  <option value="confirmed">已确认</option>
                  <option value="dismissed">已驳回</option>
                </select>
              </span>
            </div>

            {error ? <ErrorState error={error} onRetry={load} title="核验队列没读出来" /> : null}

            {loading && items.length === 0 ? (
              <div className="empty"><span className="spinner" /> 正在调工单 …</div>
            ) : items.length === 0 ? (
              <EmptyState
                title="这个条件下没有工单"
                hint="切回「全部」，或者去采集源页重跑一次采集——核验结果每次采集都会刷新。"
                action={<button className="btn btn-sm" onClick={() => flagsStore.patch({ flagType: '', reviewStatus: '' })}>重置筛选</button>}
              />
            ) : (
              <LedgerTable
                columns={columns}
                rows={items}
                rowKey={(row) => row.id}
                onRowClick={(row) => {
                  setSelected(row);
                  setNote(DEFAULT_NOTES[row.flag_type] || '');
                }}
                testId="flag-ledger"
              />
            )}
          </div>
        </div>

        <div className="stack">
          {selected ? (
            <div className="panel">
              <div className="panel-head">
                <h2>工单核验</h2>
                <StampTag kind={selected.flag_type} fresh />
              </div>
              <div className="panel-body stack" style={{ gap: 10 }}>
                <div>
                  <div className="eyebrow">{FLAG_TYPE_LABELS[selected.flag_type]} · 工单 #{selected.id}</div>
                  <h3 style={{ fontSize: '1.1rem', marginTop: 4 }}>
                    {selected.community} · {selected.layout}
                  </h3>
                  <div className="tiny muted">{selected.title}</div>
                </div>
                <div className="row spread">
                  <div>
                    <div className="tiny muted">挂牌单价</div>
                    <div className="mono" style={{ fontSize: '1.2rem' }}>{yuan(selected.unit_price)}</div>
                  </div>
                  <div className="right">
                    <div className="tiny muted">该户型中位</div>
                    <div className="mono">{yuan(selected.median_price)}</div>
                  </div>
                </div>
                <div className="row spread tiny">
                  <span>偏离 {pct(selected.deviation_pct)}</span>
                  <span>z {selected.z_score !== null ? selected.z_score.toFixed(2) : '—'}</span>
                  <span>样本 {selected.sample_size}</span>
                  <span>置信 {confidence(selected.confidence)}</span>
                </div>
                <div className="tiny muted">
                  来源 {selected.source_name || '—'} · 检出 {dateText(selected.detected_at)}
                  {selected.reviewed_by ? ` · 复核人 ${selected.reviewed_by}` : ''}
                </div>
                {selected.review_note ? <div className="note-pin">{selected.review_note}</div> : null}

                {canReview ? (
                  <>
                    <label className="field">
                      <span>复核备注（写进审计与工单）</span>
                      <textarea className="textarea" value={note} onChange={(event) => setNote(event.target.value)} />
                    </label>
                    <div className="row">
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={busy === `review-${selected.id}`}
                        onClick={() => review(selected, 'confirmed')}
                        data-testid="confirm-flag"
                      >
                        确认
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={busy === `review-${selected.id}`}
                        onClick={() => review(selected, 'dismissed')}
                      >
                        驳回
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => navigate(`/listings/${selected.listing_id}`)}>
                        打开房源详情
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="tiny muted">
                    中介客户只读：能看到核验结论与置信度，但不能确认/驳回，也不能导出行情 CSV。
                  </div>
                )}
              </div>
            </div>
          ) : (
            <EmptyState title="左侧选一条工单" hint="点任意一行，这里会显示偏离、z、置信度与复核动作。" />
          )}

          <div className="note-pin">
            <div className="eyebrow" style={{ marginBottom: 4 }}>判定口径</div>
            样本 ≥ 8 套才判定；<b>z = 0.6745 × (单价 − 中位) / MAD</b>，|z| &gt; 3 且偏离 &gt; 30% 判虚高/虚低；
            偏离落在 25%~30% 的边界样本进「待确认」，必须人工看。
          </div>
        </div>
      </div>
    </div>
  );
}
