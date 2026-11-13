import { useEffect, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { ingestApi } from '../api/ingest';
import { sourcesApi } from '../api/sources';
import { clustersApi } from '../api/clusters';
import { useToast } from '../hooks/useToast';
import { authStore } from '../stores/authStore';
import { sourcesStore } from '../stores/sourcesStore';
import { clustersStore } from '../stores/clustersStore';
import { can } from '../constants/roles';
import {
  INGEST_STATUS_LABELS,
  PLATFORM_LABELS,
  QUARANTINE_REASON_LABELS,
  SOURCE_BATCH_STATUS_LABELS,
} from '../constants/enums';
import { dateText, duration, yuan } from '../utils/format';
import { errorMessage } from '../utils/errorMessage';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import LedgerTable from '../components/common/LedgerTable';
import MetricStrip from '../components/common/MetricStrip';
import StampTag from '../components/common/StampTag';
import type { IngestRun, SourceBatch, SourceRow } from '../types/models';

export default function Sources() {
  const auth = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const role = auth.user?.role;
  const toast = useToast();
  const navigate = useNavigate();
  const canRun = can(role, 'ingest:run');
  const canEdit = can(role, 'source:write');

  const [sources, setSources] = useState<SourceRow[]>([]);
  const [runs, setRuns] = useState<IngestRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string>('');
  const [drafts, setDrafts] = useState<Record<number, { frequency: string; rate_limit_per_min: string }>>({});
  const [openRun, setOpenRun] = useState<number | null>(null);
  const [batchMap, setBatchMap] = useState<Record<number, SourceBatch[]>>({});

  async function load(force = false) {
    setLoading(true);
    try {
      await sourcesStore.load(force);
      setSources(sourcesStore.getSources());
      setRuns(sourcesStore.getRuns());
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function openBatches(runId: number) {
    if (openRun === runId) {
      setOpenRun(null);
      return;
    }
    setOpenRun(runId);
    if (!batchMap[runId]) {
      try {
        const payload = await ingestApi.batches(runId);
        setBatchMap((current) => ({ ...current, [runId]: payload.items }));
      } catch (err) {
        setError(err);
      }
    }
  }

  useEffect(() => {
    load(true);
  }, []);

  const latest = runs[0] || null;

  async function runAll() {
    setBusy('all');
    try {
      const run = await ingestApi.run();
      const isolated = run.summary?.isolated_total ?? 0;
      const replaced = run.summary?.replaced_total ?? 0;
      toast.ok(
        isolated
          ? `采集完成：替换 ${replaced} 条 / 隔离 ${isolated} 条（隔离源不进均价、工单与导出）`
          : `采集完成：${run.items_fetched} 条 / 限流 ${run.throttled_count} 次 / 去重后 ${run.dedup_count} 套`,
      );
      clustersStore.invalidate();
      await load(true);
      setOpenRun(run.id);
      setBatchMap((current) => ({ ...current, [run.id]: run.summary?.source_batches ?? [] }));
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '采集失败'));
    } finally {
      setBusy('');
    }
  }

  async function runOne(source: SourceRow) {
    setBusy(`source-${source.id}`);
    try {
      const run = await sourcesApi.runOne(source.id);
      const batch = run.summary?.source_batches?.[0];
      toast.ok(
        batch?.status === 'isolated'
          ? `${source.name} 取数不完整已整源隔离：旧挂牌不参与均价/工单/导出`
          : batch?.status === 'unchanged'
            ? `${source.name} 快照与上批一致，重复运行跳过（未改写挂牌）`
            : `${source.name} 采集完成：原子替换 ${batch?.replaced_count ?? run.items_fetched} 条`,
      );
      await load(true);
      setOpenRun(run.id);
      setBatchMap((current) => ({ ...current, [run.id]: run.summary?.source_batches ?? [] }));
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '采集失败'));
    } finally {
      setBusy('');
    }
  }

  async function saveSource(source: SourceRow) {
    const draft = drafts[source.id];
    setBusy(`save-${source.id}`);
    try {
      await sourcesStore.patchSource(source.id, {
        frequency: draft?.frequency ?? source.frequency,
        rate_limit_per_min: Number(draft?.rate_limit_per_min ?? source.rate_limit_per_min),
      });
      toast.ok(`${source.name} 的采集节奏已更新（写审计）`);
      await load(true);
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '更新失败'));
    } finally {
      setBusy('');
    }
  }

  async function toggleSource(source: SourceRow) {
    setBusy(`toggle-${source.id}`);
    try {
      await sourcesStore.patchSource(source.id, { enabled: !source.enabled });
      toast.ok(`${source.name} 已${source.enabled ? '停用' : '启用'}`);
      await load(true);
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '更新失败'));
    } finally {
      setBusy('');
    }
  }

  async function recompute() {
    setBusy('recompute');
    try {
      const result = await clustersApi.recompute();
      toast.ok(`重算完成：${result.result.cluster_count} 簇 / 重复 ${result.result.duplicate_count} 组 / 工单 ${result.result.flag_total}`);
      clustersStore.invalidate();
      await load(true);
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '重算失败'));
    } finally {
      setBusy('');
    }
  }

  const metrics = [
    { k: '启用源', v: sources.filter((source) => source.enabled).length, unit: `/ ${sources.length}`, d: '分页 + 限流各自独立' },
    { k: '最近采集条数', v: latest ? latest.items_fetched : '—', unit: '条', d: latest ? `限流 ${latest.throttled_count} 次` : '还没跑过' },
    {
      k: '整源隔离',
      v: latest?.summary?.isolated_total ?? 0,
      unit: '条',
      d: '不进均价 / 工单 / 导出',
    },
    { k: '原子替换', v: latest?.summary?.replaced_total ?? '—', unit: '条', d: latest?.summary?.recomputed === false ? '重复运行未重算' : '按本次快照落批' },
    { k: '去重结果', v: latest ? `${latest.duplicate_count}` : '—', unit: '组', d: latest ? `去重后 ${latest.dedup_count} 套` : '' },
    { k: '价格工单', v: latest ? latest.flag_count : '—', unit: '件', d: '每次有效落批自动重算' },
  ];

  const sourceColumns = [
    {
      key: 'name',
      label: '平台 / 入口',
      render: (source: SourceRow) => (
        <div>
          <div style={{ fontWeight: 600 }}>
            {source.name}
            {source.enabled ? null : <span className="plate" style={{ marginLeft: 8 }}>已停用</span>}
          </div>
          <div className="tiny muted">
            {PLATFORM_LABELS[source.platform] || source.platform} · {source.code}
          </div>
          <div className="tiny" style={{ color: 'var(--ink-faint)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {source.base_url}
          </div>
        </div>
      ),
    },
    {
      key: 'freq',
      label: '节奏 / 限流',
      render: (source: SourceRow) =>
        canEdit ? (
          <div className="row" style={{ gap: 6 }}>
            <input
              className="input"
              style={{ width: 118, padding: '4px 6px', fontSize: '0.78rem' }}
              defaultValue={source.frequency}
              onChange={(event) =>
                setDrafts((current) => ({
                  ...current,
                  [source.id]: { ...current[source.id], frequency: event.target.value },
                }))
              }
            />
            <input
              className="input mono"
              style={{ width: 64, padding: '4px 6px', fontSize: '0.78rem' }}
              defaultValue={source.rate_limit_per_min}
              onChange={(event) =>
                setDrafts((current) => ({
                  ...current,
                  [source.id]: { ...current[source.id], rate_limit_per_min: event.target.value.replace(/[^\d]/g, '') },
                }))
              }
            />
            <span className="tiny muted">/min</span>
            <button className="btn btn-sm" disabled={busy === `save-${source.id}`} onClick={() => saveSource(source)}>
              存
            </button>
          </div>
        ) : (
          <div>
            <div className="num tiny">{source.frequency}</div>
            <div className="tiny muted">{source.rate_limit_per_min} 次/分 · 每页 {source.page_size}</div>
          </div>
        ),
    },
    {
      key: 'status',
      label: '最近一次',
      render: (source: SourceRow) => (
        <div>
          {source.last_run_status ? (
            <StampTag kind={source.last_run_status} label={INGEST_STATUS_LABELS[source.last_run_status] || source.last_run_status} />
          ) : (
            <span className="tiny muted">未跑</span>
          )}
          {source.latest_batch ? (
            <div style={{ marginTop: 4 }}>
              <StampTag kind={source.latest_batch.status} label={SOURCE_BATCH_STATUS_LABELS[source.latest_batch.status] || source.latest_batch.status} />
            </div>
          ) : null}
          <div className="tiny muted">{source.last_run_at ? dateText(source.last_run_at) : '—'}</div>
        </div>
      ),
    },
    {
      key: 'items',
      label: '挂牌量',
      align: 'right' as const,
      render: (source: SourceRow) => (
        <div>
          <div className="mono">{source.listing_count}</div>
          <div className="tiny muted">
            最近入库 {source.last_run_items}
            {source.latest_batch?.status === 'isolated' ? ` · 隔离 ${source.latest_batch.isolated_count}` : ''}
          </div>
        </div>
      ),
    },
    {
      key: 'actions',
      label: '',
      align: 'right' as const,
      render: (source: SourceRow) => (
        <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
          <button
            className="btn btn-sm"
            disabled={!canRun || busy === `source-${source.id}` || !source.enabled}
            title={canRun ? '只跑这一个平台' : '当前角色无权运行采集（服务端会返回 403）'}
            onClick={() => runOne(source)}
          >
            {busy === `source-${source.id}` ? '跑…' : '单跑'}
          </button>
          {canEdit ? (
            <button className="btn btn-sm btn-ghost" disabled={busy === `toggle-${source.id}`} onClick={() => toggleSource(source)}>
              {source.enabled ? '停用' : '启用'}
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  const runColumns = [
    {
      key: 'run',
      label: '运行',
      render: (run: IngestRun) => (
        <div>
          <div className="mono tiny">{run.run_no}</div>
          <div className="tiny muted">
            {dateText(run.started_at)} · {run.trigger_label}
          </div>
        </div>
      ),
    },
    { key: 'status', label: '状态', render: (run: IngestRun) => <StampTag kind={run.status} label={INGEST_STATUS_LABELS[run.status] || run.status} /> },
    {
      key: 'items',
      label: '条数',
      align: 'right' as const,
      render: (run: IngestRun) => (
        <div>
          <div className="mono">{run.items_fetched}</div>
          <div className="tiny muted">新增 {run.created_count} / 更新 {run.updated_count}</div>
        </div>
      ),
    },
    {
      key: 'throttle',
      label: '限流',
      align: 'right' as const,
      render: (run: IngestRun) => (
        <div>
          <div className={`mono ${run.throttled_count ? '' : 'muted'}`}>{run.throttled_count} 次</div>
          <div className="tiny muted">退避 {run.backoff_ms} ms</div>
        </div>
      ),
    },
    {
      key: 'result',
      label: '去重 / 工单',
      align: 'right' as const,
      render: (run: IngestRun) => (
        <div>
          <div className="mono">{run.duplicate_count} 组</div>
          <div className="tiny muted">{run.dedup_count} 套 · 工单 {run.flag_count}</div>
        </div>
      ),
    },
    { key: 'duration', label: '耗时', align: 'right' as const, render: (run: IngestRun) => <span className="mono tiny">{duration(run.duration_ms)}</span> },
    {
      key: 'open',
      label: '',
      align: 'right' as const,
      render: (run: IngestRun) => (
        <button className="btn btn-sm btn-ghost" onClick={() => openBatches(run.id)}>
          {openRun === run.id ? '收起' : '明细'}
        </button>
      ),
    },
  ];

  const activeRun = runs.find((run) => run.id === openRun) || null;
  const activeBatches = activeRun ? batchMap[activeRun.id] ?? activeRun.summary?.source_batches ?? [] : [];

  return (
    <div className="stack fade-in">
      <MetricStrip items={metrics} />

      <div className="panel">
        <div className="panel-head">
          <h2>采集源</h2>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-sm" onClick={recompute} disabled={!canRun || busy === 'recompute'}>
              {busy === 'recompute' ? '重算…' : '只重算去重/核验'}
            </button>
            <button
              className="btn btn-primary"
              onClick={runAll}
              disabled={!canRun || busy === 'all'}
              title={canRun ? '跑全部启用的源（含 429 退避）' : '中介客户无权运行采集，服务端会返回 403'}
              data-testid="run-ingest"
            >
              {busy === 'all' ? '采集运行中 …' : '运行采集（5 源）'}
            </button>
          </div>
        </div>
        <div className="panel-body">
          {error ? <ErrorState error={error} onRetry={() => load(true)} title="采集源没读出来" /> : null}
          {!error && loading && sources.length === 0 ? (
            <div className="empty"><span className="spinner" /> 正在读源配置 …</div>
          ) : null}
          {!error && sources.length > 0 ? (
            <LedgerTable columns={sourceColumns} rows={sources} rowKey={(row) => row.id} testId="source-ledger" />
          ) : null}
          {!canRun ? (
            <div className="tiny muted" style={{ marginTop: 10 }}>
              当前角色（{role}）只能看采集结果；运行采集、重算与改源配置由研究组长 / 数据专员操作，
              直接调接口会拿到 403。
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>运行记录</h2>
          <span className="tiny muted">每次运行记录 分页 / 429 退避 / 去重 / 工单 四段结果</span>
        </div>
        <div className="panel-body stack" style={{ gap: 12 }}>
          {runs.length === 0 ? (
            <EmptyState title="还没有运行记录" hint="点「运行采集（5 源）」跑第一次；seed 只会写历史记录。" />
          ) : (
            <LedgerTable columns={runColumns} rows={runs} rowKey={(row) => row.id} testId="run-ledger" />
          )}

          {activeRun ? (
            <div className="panel" style={{ background: 'var(--paper-2)' }}>
              <div className="panel-head">
                <h3 style={{ fontSize: '0.94rem' }}>{activeRun.run_no} · 明细</h3>
                <span className="tiny muted">{activeRun.message}</span>
              </div>
              <div className="panel-body stack" style={{ gap: 12 }}>
                {activeBatches.length ? (
                  <div>
                    <div className="eyebrow" style={{ marginBottom: 4 }}>
                      逐源落批核对 · 收到 / 隔离 / 替换
                      {activeRun.summary?.recomputed === false ? (
                        <span className="plate" style={{ marginLeft: 8 }}>本批无落批变化，未触发重算</span>
                      ) : null}
                    </div>
                    <div className="ledger-wrap">
                      <table className="ledger" data-testid="source-batch-ledger">
                        <thead>
                          <tr>
                            <th>来源</th>
                            <th className="right">页（取/应）</th>
                            <th className="right">收到</th>
                            <th className="right">隔离</th>
                            <th className="right">替换（新/更/删）</th>
                            <th>结果 / 原因</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeBatches.map((batch) => (
                            <tr key={batch.id} className={batch.status === 'isolated' ? 'is-quarantined' : ''}>
                              <td className="mono tiny">{batch.source_code}</td>
                              <td className="num right">
                                {batch.pages_fetched} / {batch.pages_expected || '—'}
                              </td>
                              <td className="num right">{batch.received_count}</td>
                              <td className="num right">{batch.isolated_count || '—'}</td>
                              <td className="num right">
                                {batch.status === 'replaced'
                                  ? `${batch.replaced_count}（${batch.created_count}/${batch.updated_count}/${batch.deleted_count}）`
                                  : '—'}
                              </td>
                              <td>
                                <StampTag kind={batch.status} label={SOURCE_BATCH_STATUS_LABELS[batch.status] || batch.status} />
                                {batch.reason ? (
                                  <div className="tiny muted" style={{ marginTop: 3 }}>
                                    {QUARANTINE_REASON_LABELS[batch.reason] || batch.reason}
                                  </div>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                <div className="row" style={{ gap: 18 }}>
                  <div>
                    <div className="tiny muted">页面</div>
                    <div className="mono">{activeRun.pages_fetched}</div>
                  </div>
                  <div>
                    <div className="tiny muted">解析</div>
                    <div className="mono">{activeRun.items_fetched}</div>
                  </div>
                  <div>
                    <div className="tiny muted">429 退避</div>
                    <div className="mono">{activeRun.throttled_count} 次 / {activeRun.backoff_ms} ms</div>
                  </div>
                  <div>
                    <div className="tiny muted">面积缺失</div>
                    <div className="mono">{activeRun.summary?.unknown_area ?? 0} 条</div>
                  </div>
                  <div>
                    <div className="tiny muted">相似对 / 连边</div>
                    <div className="mono">
                      {activeRun.summary?.pair_count ?? 0} / {activeRun.summary?.edge_count ?? 0}
                    </div>
                  </div>
                </div>

                {activeRun.summary?.throttle_log?.length ? (
                  <div>
                    <div className="eyebrow" style={{ marginBottom: 4 }}>限流退避</div>
                    <div className="ledger-wrap">
                      <table className="ledger">
                        <thead>
                          <tr>
                            <th>平台</th>
                            <th>页</th>
                            <th>状态</th>
                            <th>等待</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeRun.summary.throttle_log.map((entry, index) => (
                            <tr key={`${entry.source}-${index}`}>
                              <td>{entry.source}</td>
                              <td className="num">{entry.page}</td>
                              <td>
                                <span className="stamp uncertain">{entry.status}</span>
                              </td>
                              <td className="mono">{entry.wait_ms} ms</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                {activeRun.summary?.blocks?.length ? (
                  <div>
                    <div className="eyebrow" style={{ marginBottom: 4 }}>均价刷新（去重前 → 去重后）</div>
                    <div className="ledger-wrap">
                      <table className="ledger">
                        <thead>
                          <tr>
                            <th>小区 · 户型</th>
                            <th className="right">样本</th>
                            <th className="right">去重前</th>
                            <th className="right">去重后</th>
                            <th className="right">中位</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {activeRun.summary.blocks.map((block) => (
                            <tr key={`${block.community}-${block.layout}`}>
                              <td>
                                {block.community} · {block.layout}
                              </td>
                              <td className="num right">{block.primary_count}</td>
                              <td className="num right">{block.naive_mean ? yuan(block.naive_mean) : '—'}</td>
                              <td className="num right" style={{ color: 'var(--ochre)' }}>
                                {block.dedup_mean ? yuan(block.dedup_mean) : '—'}
                              </td>
                              <td className="num right">{block.median_price ? yuan(block.median_price) : '—'}</td>
                              <td className="right">
                                <button className="btn btn-sm btn-ghost" onClick={() => navigate('/listings')}>
                                  去池子看
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
