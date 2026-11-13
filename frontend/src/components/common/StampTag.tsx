/** 印章标签：虚高 / 虚低 / 待确认 / 重复 / 复核态 / 落批态。多页共用。 */
const LABELS: Record<string, string> = {
  high: '虚高',
  low: '虚低',
  uncertain: '待确认',
  dup: '重复挂牌',
  confirmed: '已确认',
  dismissed: '已驳回',
  pending: '待复核',
  success: '成功',
  partial: '部分成功',
  failed: '失败',
  running: '运行中',
  replaced: '已替换',
  unchanged: '重复跳过',
  isolated: '已隔离',
  quarantined: '整源隔离',
};

export default function StampTag({
  kind,
  label,
  fresh = false,
  title,
}: {
  kind: string;
  label?: string;
  fresh?: boolean;
  title?: string;
}) {
  return (
    <span className={`stamp ${kind} ${fresh ? 'entered' : ''}`} title={title} data-flag-type={kind}>
      {label || LABELS[kind] || kind}
    </span>
  );
}
