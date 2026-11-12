import { useState, useSyncExternalStore } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { listingsApi } from '../api/listings';
import { flagsApi } from '../api/flags';
import { useAsync } from '../hooks/useAsync';
import { useToast } from '../hooks/useToast';
import { authStore } from '../stores/authStore';
import { can } from '../constants/roles';
import { FLAG_TYPE_LABELS, REVIEW_LABELS } from '../constants/enums';
import { area, confidence, dateText, floorText, pct, shortDate, yuan } from '../utils/format';
import { errorMessage } from '../utils/errorMessage';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import PriceSeriesChart from '../components/common/PriceSeriesChart';
import StampTag from '../components/common/StampTag';

export default function ListingDetail() {
  const { listingId } = useParams();
  const id = Number(listingId);
  const navigate = useNavigate();
  const auth = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const role = auth.user?.role;
  const toast = useToast();
  const [note, setNote] = useState('研究组已电话核实：业主确认是试探价，按中位价入库');
  const [priceInput, setPriceInput] = useState('');
  const [busy, setBusy] = useState(false);

  const { data, loading, error, reload } = useAsync(() => listingsApi.detail(id), [id]);

  async function review(reviewStatus: 'confirmed' | 'dismissed') {
    if (!data?.flag) return;
    setBusy(true);
    try {
      await flagsApi.review(data.flag.id, reviewStatus, note);
      toast.ok(reviewStatus === 'confirmed' ? '工单已确认，行情表按去重口径更新' : '工单已驳回，保留原始挂牌价');
      reload();
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '复核失败'));
    } finally {
      setBusy(false);
    }
  }

  async function fixPrice() {
    const value = Number(priceInput);
    if (!value) {
      toast.error('先填一个单价（元/㎡）');
      return;
    }
    setBusy(true);
    try {
      await listingsApi.fixPrice(id, value, '数据专员按门店回价修正');
      toast.ok('单价已修正，中位/MAD 与工单已按新值重算');
      setPriceInput('');
      reload();
    } catch (err) {
      toast.error(errorMessage((err as { payload?: unknown }).payload, '修正失败'));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) {
    return <div className="empty"><span className="spinner" /> 正在把三个平台的挂牌并排摆开 …</div>;
  }
  if (error) {
    return <ErrorState error={error} onRetry={reload} title="这套房没读出来" />;
  }
  if (!data) {
    return (
      <EmptyState
        title="记录板上没有这套房"
        hint="可能被重新采集覆盖了，回挂牌池重新选一条。"
        action={<button className="btn btn-sm" onClick={() => navigate('/listings')}>回挂牌池</button>}
      />
    );
  }

  const { listing, members, block, flag, price_series } = data;
  const canReview = can(role, 'flag:review');
  const canWrite = can(role, 'listing:write');
  const median = block?.median_price || null;
  const dedupMean = block?.dedup_mean || null;
  const naiveMean = block?.naive_mean || null;
  const inflation = block?.inflation_pct ?? null;
  const vsMedian = listing.unit_price && median ? ((listing.unit_price - median) / median) * 100 : null;

  return (
    <div className="stack fade-in">
      <div className="row">
        <button className="btn btn-sm" onClick={() => navigate('/listings')}>
          ← 回挂牌池
        </button>
        <span className="plate">房源 #{listing.id}</span>
        <span className="plate">{listing.source_listing_no}</span>
        {listing.cluster_size > 1 ? <StampTag kind="dup" label={`同簇 ${listing.cluster_size} 条 / ${listing.platform_count} 个平台`} /> : null}
      </div>

      <div className="panel">
        <div className="panel-body detail-head">
          <div>
            <div className="eyebrow">{listing.community} · {listing.layout} · 挂牌 {shortDate(listing.list_date)}</div>
            <h2 style={{ fontSize: '1.5rem', margin: '4px 0 6px' }}>
              {listing.community} {listing.layout} <span className="mono tiny">{area(listing.area_sqm)}</span>
            </h2>
            <div className="tiny muted" style={{ maxWidth: 620 }}>
              {listing.title}
            </div>
            <div className="row" style={{ marginTop: 12, gap: 18, fontSize: '0.8rem' }}>
              <div>
                <div className="tiny muted">楼层</div>
                {floorText(listing.floor, listing.total_floors, listing.floor_band)}
              </div>
              <div>
                <div className="tiny muted">来源</div>
                {listing.source_name}
              </div>
              <div>
                <div className="tiny muted">字段完整度</div>
                <span className="mono">{confidence(listing.completeness)}</span>
              </div>
              <div>
                <div className="tiny muted">联系方式</div>
                {listing.agent_contact ? (
                  <span className="mono">{listing.agent_contact}</span>
                ) : (
                  <span className="tiny muted">当前角色不可见</span>
                )}
              </div>
            </div>
          </div>
          <div className="right">
            <div className="big-price">
              {listing.unit_price ? yuan(listing.unit_price) : '—'}
              <small>元/㎡</small>
            </div>
            <div className="tiny muted">
              总价 {listing.total_price_wan ? `${listing.total_price_wan.toFixed(1)} 万` : '—'}
            </div>
            {vsMedian !== null ? (
              <div style={{ marginTop: 8 }}>
                <span className={`stamp ${vsMedian > 0 ? 'high' : 'low'}`}>对中位 {pct(vsMedian)}</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h2>价格序列 · 同簇跨平台</h2>
              <div className="legend">
                <span><i style={{ background: 'oklch(0.432 0.118 32)' }} />挂牌点</span>
                <span><i style={{ background: 'oklch(0.652 0.098 74)' }} />中位单价</span>
              </div>
            </div>
            <div className="panel-body">
              <PriceSeriesChart points={price_series} median={median} dedupMean={dedupMean} />
              <div className="tiny muted" style={{ marginTop: 6 }}>
                虚线是该小区×户型「去重后」的中位单价；同一套房在各平台的挂牌日越晚，越可能是往上试探的价。
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>多平台并排</h2>
              <span className="tiny muted">相似度 = 面积 0.30 / 楼层 0.20 / 标题 Jaccard 0.25 / 单价接近 0.25</span>
            </div>
            <div className="panel-body">
              {members.length === 0 ? (
                <EmptyState title="只有一个平台挂了这套房" hint="去采集源页确认其它平台今天是否跑成功。" />
              ) : (
                <div className="members">
                  {members.map((member) => (
                    <div className={`member ${member.is_primary ? 'primary' : ''}`} key={member.id}>
                      <div className="row spread">
                        <h4>{member.source_name}</h4>
                        {member.is_primary ? <span className="plate">主房源</span> : null}
                      </div>
                      <div className="t">{member.title}</div>
                      <div className="row spread">
                        <div className="mono" style={{ fontSize: '1.05rem' }}>
                          {member.unit_price ? yuan(member.unit_price) : '—'}
                          <span className="tiny muted"> 元/㎡</span>
                        </div>
                        <div className="tiny muted mono">
                          {member.similarity !== null ? `相似 ${member.similarity.toFixed(3)}` : '基准'}
                        </div>
                      </div>
                      <div className="tiny muted">
                        {shortDate(member.list_date)} · {floorText(member.floor, null, member.floor_band)} · {member.source_listing_no}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>

        <div className="stack">
          <div className="panel">
            <div className="panel-head">
              <h2>小区×户型 均价口径</h2>
              <span className="plate">样本 {block?.primary_count ?? 0} 套</span>
            </div>
            <div className="panel-body stack" style={{ gap: 10 }}>
              <div>
                <div className="row spread tiny muted">
                  <span>去重前均价（含重复挂牌）</span>
                  <span className="mono">{naiveMean ? `${yuan(naiveMean)} 元/㎡` : '—'}</span>
                </div>
                <div className="compare-bar" style={{ marginTop: 4 }}>
                  <i style={{ width: '100%', background: 'oklch(0.812 0.02 76)' }} />
                </div>
              </div>
              <div>
                <div className="row spread tiny muted">
                  <span>去重后均价（主房源口径）</span>
                  <span className="mono">{dedupMean ? `${yuan(dedupMean)} 元/㎡` : '—'}</span>
                </div>
                <div className="compare-bar" style={{ marginTop: 4 }}>
                  <i
                    style={{
                      width: naiveMean && dedupMean ? `${Math.min(100, (dedupMean / naiveMean) * 100)}%` : '0%',
                      background: 'oklch(0.432 0.118 32)',
                    }}
                  />
                </div>
              </div>
              <div className="tiny muted">
                中位 {median ? yuan(median) : '—'} · MAD {block?.mad ? yuan(block.mad) : '—'} · 重复挂牌把均价抬高
                <b className="mono" style={{ color: 'var(--ochre)' }}> {inflation !== null ? pct(inflation) : '—'}</b>
                （同一套房被 2~3 个平台重复计权）。
              </div>
              <div className="annot">研究组口径：先看核验队列里的虚高工单，再决定周报发哪个均价。</div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              <h2>价格核验</h2>
              {flag ? <StampTag kind={flag.flag_type} fresh /> : <span className="plate">无异常</span>}
            </div>
            <div className="panel-body stack" style={{ gap: 10 }}>
              {flag ? (
                <>
                  <div className="row spread">
                    <span className="tiny muted">{FLAG_TYPE_LABELS[flag.flag_type]}</span>
                    <span className={`stamp ${flag.review_status}`}>{REVIEW_LABELS[flag.review_status]}</span>
                  </div>
                  <div className="row spread">
                    <div>
                      <div className="tiny muted">单价 / 中位</div>
                      <div className="mono">
                        {yuan(flag.unit_price)} / {yuan(flag.median_price)}
                      </div>
                    </div>
                    <div className="right">
                      <div className="tiny muted">偏离 / 稳健 z</div>
                      <div className="mono">
                        {pct(flag.deviation_pct)} / {flag.z_score !== null ? flag.z_score.toFixed(2) : '—'}
                      </div>
                    </div>
                  </div>
                  <div className="row spread">
                    <div>
                      <div className="tiny muted">置信度</div>
                      <div className="mono">{confidence(flag.confidence)}</div>
                    </div>
                    <div className="right">
                      <div className="tiny muted">样本</div>
                      <div className="mono">{flag.sample_size} 套</div>
                    </div>
                  </div>
                  {flag.review_note ? <div className="tiny muted">复核备注：{flag.review_note}</div> : null}
                  {canReview ? (
                    <>
                      <label className="field">
                        <span>复核备注</span>
                        <textarea className="textarea" value={note} onChange={(event) => setNote(event.target.value)} />
                      </label>
                      <div className="row">
                        <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => review('confirmed')}>
                          确认虚高/虚低
                        </button>
                        <button className="btn btn-sm" disabled={busy} onClick={() => review('dismissed')}>
                          驳回（按原价保留）
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="tiny muted">中介客户只读：复核动作由数据专员 / 研究组长完成。</div>
                  )}
                </>
              ) : (
                <div className="tiny muted">
                  这套房的单价在「中位 ±30%」以内，没有生成工单。想看整批异常去
                  <a href="/flags"> 核验队列</a>。
                </div>
              )}
            </div>
          </div>

          {canWrite ? (
            <div className="panel">
              <div className="panel-head">
                <h2>修正挂牌单价</h2>
                <span className="tiny muted">门店回价后手动改</span>
              </div>
              <div className="panel-body stack" style={{ gap: 8 }}>
                <label className="field">
                  <span>新单价（元/㎡）</span>
                  <input
                    className="input mono"
                    placeholder={listing.unit_price ? String(listing.unit_price) : '例如 58900'}
                    value={priceInput}
                    onChange={(event) => setPriceInput(event.target.value.replace(/[^\d]/g, ''))}
                  />
                </label>
                <button className="btn btn-sm" disabled={busy} onClick={fixPrice}>
                  提交修正并重算
                </button>
                <div className="tiny muted">修正会写审计日志，并触发该批次的中位/MAD 与工单重算。</div>
              </div>
            </div>
          ) : (
            <div className="note-pin">
              中介客户视图：能看到挂牌、同簇对比与价格核验结论，但看不到原始联系方式，也不能改价。
            </div>
          )}

          <div className="note-pin">
            <div className="eyebrow" style={{ marginBottom: 4 }}>手写批注</div>
            同一套房在 {listing.platform_count} 个平台出现，价差来自挂牌时间和业主心态；
            均价要按去重后的主房源算，否则高价房被多计一次。
          </div>
        </div>
      </div>
    </div>
  );
}
