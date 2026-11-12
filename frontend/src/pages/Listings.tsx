import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { listingsApi } from '../api/listings';
import { useAsync } from '../hooks/useAsync';
import { useDebouncedValue } from '../hooks/useFilters';
import { listingsStore } from '../stores/listingsStore';
import { clustersStore } from '../stores/clustersStore';
import { authStore } from '../stores/authStore';
import { can } from '../constants/roles';
import { FLAG_TYPE_LABELS, FLAG_TYPE_ORDER, LAYOUT, SORT_OPTIONS } from '../constants/enums';
import { area, floorText, pct, shortDate, yuan } from '../utils/format';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import FilterBar from '../components/common/FilterBar';
import LedgerTable from '../components/common/LedgerTable';
import MetricStrip from '../components/common/MetricStrip';
import StampTag from '../components/common/StampTag';
import type { ListingRow } from '../types/models';

export default function Listings() {
  const state = useSyncExternalStore(listingsStore.subscribe, listingsStore.getState);
  const auth = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const navigate = useNavigate();
  const [search, setSearch] = useState(state.q);
  const debounced = useDebouncedValue(search, 320);
  const [clusterList, setClusterList] = useState<{ id: number; community: string; layout: string; member_count: number; platform_count: number; primary_listing_id: number }[]>([]);
  const [showClusters, setShowClusters] = useState(true);

  useEffect(() => {
    if (debounced !== state.q) listingsStore.patch({ q: debounced });
  }, [debounced, state.q]);

  const { data: options } = useAsync(() => listingsApi.options(), []);
  const { data, loading, error, reload } = useAsync(
    () =>
      listingsApi.list({
        q: state.q || undefined,
        community: state.community || undefined,
        layout: state.layout || undefined,
        source_id: state.sourceId || undefined,
        flag_type: state.flagType || undefined,
        duplicate_only: state.duplicateOnly,
        primary_only: state.primaryOnly,
        sort: state.sort,
        order: state.order,
        page: state.page,
        page_size: state.pageSize,
      }),
    [
      state.q,
      state.community,
      state.layout,
      state.sourceId,
      state.flagType,
      state.duplicateOnly,
      state.primaryOnly,
      state.sort,
      state.order,
      state.page,
      state.pageSize,
    ],
  );

  useEffect(() => {
    if (data) listingsStore.setCache(data);
  }, [data]);

  useEffect(() => {
    let alive = true;
    clustersStore
      .ensure()
      .then((items) => {
        if (!alive) return;
        setClusterList(
          items
            .slice()
            .sort((a, b) => b.member_count - a.member_count)
            .slice(0, 8)
            .map((row) => ({
              id: row.id,
              community: row.community,
              layout: row.layout,
              member_count: row.member_count,
              platform_count: row.platform_count,
              primary_listing_id: row.primary_listing_id,
            })),
        );
      })
      .catch(() => setClusterList([]));
    return () => {
      alive = false;
    };
  }, []);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const sums = data?.sums;

  const metrics = useMemo(
    () => [
      { k: '挂牌总数', v: data ? data.total : '—', unit: '条', d: '5 个平台合计' },
      { k: '本页均价', v: sums?.page_avg_unit_price ? yuan(sums.page_avg_unit_price) : '—', unit: '元/㎡', d: '含重复挂牌' },
      { k: '本页单价区间', v: `${sums?.page_min_unit_price ? yuan(sums.page_min_unit_price) : '—'} ~ ${sums?.page_max_unit_price ? yuan(sums.page_max_unit_price) : '—'}`, d: '元/㎡' },
      { k: '本页重复行', v: sums?.duplicate_rows ?? 0, unit: '条', d: '同簇多平台挂牌' },
      { k: '面积缺失', v: sums?.unknown_area ?? 0, unit: '条', d: '不计入均价' },
    ],
    [data, sums],
  );

  const role = auth.user?.role;
  const canWrite = can(role, 'listing:write');

  const columns = [
    {
      key: 'house',
      label: '房源',
      render: (row: ListingRow) => (
        <div>
          <div style={{ fontWeight: 600 }}>
            {row.community} · {row.layout}
            {row.cluster_size > 1 ? <span className="plate" style={{ marginLeft: 8 }}>NO.{String(row.cluster_id).padStart(2, '0')}</span> : null}
          </div>
          <div className="tiny muted">
            {area(row.area_sqm)} · {floorText(row.floor, row.total_floors, row.floor_band)}
          </div>
          <div className="tiny" style={{ color: 'var(--ink-faint)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {row.title}
          </div>
        </div>
      ),
    },
    {
      key: 'price',
      label: '单价',
      align: 'right' as const,
      render: (row: ListingRow) =>
        row.unit_price ? (
          <div>
            <div className="price">{yuan(row.unit_price)}</div>
            <div className="tiny muted">元/㎡</div>
          </div>
        ) : (
          <div className="tiny muted">面积缺失<br />不计均价</div>
        ),
    },
    {
      key: 'total',
      label: '总价',
      align: 'right' as const,
      render: (row: ListingRow) => <span className="num">{row.total_price_wan ? `${row.total_price_wan.toFixed(1)} 万` : '—'}</span>,
    },
    {
      key: 'date',
      label: '挂牌',
      render: (row: ListingRow) => (
        <div>
          <div className="num tiny">{shortDate(row.list_date)}</div>
          <div className="tiny muted">{row.source_name}</div>
          <div className="tiny" style={{ color: 'var(--ink-faint)' }}>{row.source_listing_no}</div>
        </div>
      ),
    },
    {
      key: 'marks',
      label: '标记',
      render: (row: ListingRow) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {row.cluster_size > 1 ? (
            <StampTag kind="dup" label={`重复 ${row.cluster_size}`} title={`同簇 ${row.platform_count} 个平台`} />
          ) : null}
          {row.flag_type ? (
            <StampTag
              kind={row.flag_type}
              label={`${FLAG_TYPE_LABELS[row.flag_type] || row.flag_type} ${row.deviation_pct ? pct(row.deviation_pct) : ''}`}
            />
          ) : null}
          {row.review_status && row.review_status !== 'pending' ? (
            <StampTag kind={row.review_status} />
          ) : null}
        </div>
      ),
    },
    {
      key: 'actions',
      label: '',
      align: 'right' as const,
      render: (row: ListingRow) => (
        <button
          className="btn btn-sm"
          onClick={(event) => {
            event.stopPropagation();
            navigate(`/listings/${row.id}`);
          }}
        >
          看板
        </button>
      ),
    },
  ];

  return (
    <div className="stack fade-in">
      <MetricStrip items={metrics} />

      <div className="panel">
        <div className="panel-head">
          <h2>挂牌池</h2>
          <div className="tiny muted">
            同一套房跨平台挂牌会标「重复 n」；单价按去重口径排序才有可比性。
            {canWrite ? null : ' 当前角色为只读，修正单价请用数据专员账号。'}
          </div>
        </div>
        <div className="panel-body stack" style={{ gap: 12 }}>
          <FilterBar
            right={
              <div className="row" style={{ gap: 6 }}>
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    setSearch('');
                    listingsStore.reset();
                  }}
                >
                  清空筛选
                </button>
                <button className="btn btn-sm" onClick={reload}>
                  刷新
                </button>
              </div>
            }
          >
            <label className="field grow">
              <span>搜小区 / 标题</span>
              <input
                className="input"
                value={search}
                placeholder="例如 兰亭苑 / 精装"
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className="field">
              <span>小区</span>
              <select className="select" value={state.community} onChange={(event) => listingsStore.patch({ community: event.target.value })}>
                <option value="">全部</option>
                {(options?.communities || []).map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>户型</span>
              <select className="select" value={state.layout} onChange={(event) => listingsStore.patch({ layout: event.target.value })}>
                <option value="">全部</option>
                {(options?.layouts || LAYOUT).map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>来源</span>
              <select
                className="select"
                value={String(state.sourceId)}
                onChange={(event) => listingsStore.patch({ sourceId: event.target.value ? Number(event.target.value) : '' })}
              >
                <option value="">全部</option>
                {(options?.sources || []).map((source) => (
                  <option key={source.id} value={source.id}>{source.name}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>价格标记</span>
              <select className="select" value={state.flagType} onChange={(event) => listingsStore.patch({ flagType: event.target.value })}>
                <option value="">全部</option>
                {FLAG_TYPE_ORDER.map((item) => (
                  <option key={item} value={item}>{FLAG_TYPE_LABELS[item]}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>排序</span>
              <select className="select" value={state.sort} onChange={(event) => listingsStore.patch({ sort: event.target.value })}>
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>重复</span>
              <select
                className="select"
                value={state.duplicateOnly ? 'yes' : state.primaryOnly ? 'primary' : 'all'}
                onChange={(event) => {
                  const value = event.target.value;
                  listingsStore.patch({
                    duplicateOnly: value === 'yes',
                    primaryOnly: value === 'primary',
                  });
                }}
              >
                <option value="all">全部</option>
                <option value="yes">仅重复组</option>
                <option value="primary">仅去重后</option>
              </select>
            </label>
          </FilterBar>

          {error ? <ErrorState error={error} onRetry={reload} title="挂牌池没读出来" /> : null}

          {loading && !data ? (
            <div className="empty"><span className="spinner" /> 正在翻牌 …</div>
          ) : data && data.items.length === 0 ? (
            <EmptyState
              title="这个筛选条件下没有挂牌"
              hint="把「重复」切回全部，或清空搜索词；也可以去采集源页确认今天的数据已经跑过。"
              action={<button className="btn btn-sm" onClick={() => listingsStore.reset()}>清空筛选</button>}
            />
          ) : data ? (
            <>
              <LedgerTable
                columns={columns}
                rows={data.items}
                rowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/listings/${row.id}`)}
                rowClassName={(row) => (row.cluster_size > 1 ? 'is-dup' : '')}
                testId="listing-ledger"
              />
              <div className="row spread">
                <div className="tiny muted">
                  第 {data.page} / {totalPages} 页 · 共 {data.total} 条
                  {loading ? ' · 刷新中' : ''}
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <button className="btn btn-sm" disabled={data.page <= 1} onClick={() => listingsStore.patch({ page: data.page - 1 })}>
                    上一页
                  </button>
                  <button
                    className="btn btn-sm"
                    disabled={data.page >= totalPages}
                    onClick={() => listingsStore.patch({ page: data.page + 1 })}
                  >
                    下一页
                  </button>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>重复挂牌最多的组</h2>
          <button className="btn btn-sm btn-ghost" onClick={() => setShowClusters((value) => !value)}>
            {showClusters ? '收起' : '展开'}
          </button>
        </div>
        {showClusters ? (
          <div className="panel-body">
            {clusterList.length === 0 ? (
              <EmptyState title="还没有去重结果" hint="去「采集源与运行」跑一次采集，去重簇会自动生成。" />
            ) : (
              <div className="ledger-wrap">
                <table className="ledger">
                  <thead>
                    <tr>
                      <th>小区 · 户型</th>
                      <th>簇内挂牌</th>
                      <th>覆盖平台</th>
                      <th>主房源</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {clusterList.map((cluster) => (
                      <tr key={cluster.id}>
                        <td>
                          {cluster.community} · {cluster.layout}
                        </td>
                        <td className="num">{cluster.member_count} 条</td>
                        <td className="num">{cluster.platform_count} 个</td>
                        <td className="mono tiny">#{cluster.primary_listing_id}</td>
                        <td className="right">
                          <button className="btn btn-sm" onClick={() => navigate(`/listings/${cluster.primary_listing_id}`)}>
                            主房源看板
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
