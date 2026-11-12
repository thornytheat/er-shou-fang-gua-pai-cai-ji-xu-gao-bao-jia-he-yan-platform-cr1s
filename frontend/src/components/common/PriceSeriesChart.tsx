import type { PriceSeriesPoint } from '../../types/models';
import { shortDate, yuan } from '../../utils/format';

/**
 * 价格序列（SVG 自绘，无图表库）：
 * 横轴 = 挂牌日，纵轴 = 单价，虚线 = 该小区×户型中去重后的中位单价。
 * 同一簇的多平台挂牌会在图上并列，能直接看出「谁在往上试探」。
 */
export default function PriceSeriesChart({
  points,
  median,
  dedupMean,
}: {
  points: PriceSeriesPoint[];
  median?: number | null;
  dedupMean?: number | null;
}) {
  const usable = points.filter((point) => point.unit_price && point.date);
  if (usable.length === 0) {
    return (
      <div className="empty" style={{ minHeight: 160 }}>
        <strong>这一簇还没有可比的价格点</strong>
        <div className="tiny muted">挂牌缺少面积或单价时不计入序列，可回到挂牌池换一条。</div>
      </div>
    );
  }

  const width = 640;
  const height = 208;
  const padding = { left: 52, right: 16, top: 16, bottom: 26 };
  const prices = usable.map((point) => Number(point.unit_price));
  if (median) prices.push(median);
  if (dedupMean) prices.push(dedupMean);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const span = Math.max(maxPrice - minPrice, 1200);
  const low = minPrice - span * 0.18;
  const high = maxPrice + span * 0.18;

  const dates = usable.map((point) => new Date(point.date as string).getTime());
  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const dateSpan = Math.max(maxDate - minDate, 86400000);

  const x = (dateText: string) =>
    padding.left +
    ((new Date(dateText).getTime() - minDate) / dateSpan) * (width - padding.left - padding.right);
  const y = (price: number) =>
    padding.top + (1 - (price - low) / (high - low)) * (height - padding.top - padding.bottom);

  const ordered = [...usable].sort(
    (a, b) => new Date(a.date as string).getTime() - new Date(b.date as string).getTime(),
  );
  const line = ordered.map((point) => `${x(point.date as string)},${y(Number(point.unit_price))}`).join(' ');
  const ticks = [low + (high - low) * 0.15, (low + high) / 2, high - (high - low) * 0.15];

  return (
    <svg className="series" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="挂牌单价序列">
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={y(tick)}
            y2={y(tick)}
            stroke="oklch(0.86 0.014 78)"
            strokeDasharray="2 4"
          />
          <text x={8} y={y(tick) + 4} fontSize="9" fill="oklch(0.52 0.02 66)" fontFamily="IBM Plex Mono, monospace">
            {yuan(tick)}
          </text>
        </g>
      ))}

      {median ? (
        <g>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={y(median)}
            y2={y(median)}
            stroke="oklch(0.652 0.098 74)"
            strokeDasharray="7 5"
            strokeWidth="1.4"
          />
          <text
            x={width - padding.right}
            y={y(median) - 5}
            textAnchor="end"
            fontSize="9"
            fill="oklch(0.55 0.09 74)"
            fontFamily="IBM Plex Mono, monospace"
          >
            中位 {yuan(median)}
          </text>
        </g>
      ) : null}

      <polyline points={line} fill="none" stroke="oklch(0.552 0.098 34)" strokeWidth="1.6" />

      {ordered.map((point, index) => (
        <g key={`${point.label}-${index}`}>
          <circle
            cx={x(point.date as string)}
            cy={y(Number(point.unit_price))}
            r={point.is_primary ? 5 : 3.6}
            fill={point.is_primary ? 'oklch(0.432 0.118 32)' : 'oklch(0.962 0.010 84)'}
            stroke="oklch(0.432 0.118 32)"
            strokeWidth="1.4"
          />
          <title>{`${point.source_name} · ${point.date} · ${yuan(point.unit_price)} 元/㎡`}</title>
        </g>
      ))}

      <line
        x1={padding.left}
        x2={width - padding.right}
        y1={height - padding.bottom}
        y2={height - padding.bottom}
        stroke="oklch(0.712 0.028 74)"
      />
      <text x={padding.left} y={height - 8} fontSize="9" fill="oklch(0.52 0.02 66)" fontFamily="IBM Plex Mono, monospace">
        {shortDate(ordered[0].date)}
      </text>
      <text
        x={width - padding.right}
        y={height - 8}
        textAnchor="end"
        fontSize="9"
        fill="oklch(0.52 0.02 66)"
        fontFamily="IBM Plex Mono, monospace"
      >
        {shortDate(ordered[ordered.length - 1].date)}
      </text>
    </svg>
  );
}
