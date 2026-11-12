export function yuan(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('zh-CN').format(Math.round(value));
}

export function wan(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function area(value: number | null | undefined): string {
  if (value === null || value === undefined) return '面积缺失';
  return `${Math.round(value)}㎡`;
}

export function floorText(floor: number | null, total: number | null, band: string | null): string {
  if (floor && total) return `${floor}/${total} 层`;
  if (band) return band;
  return '楼层未知';
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.slice(5, 10);
}

export function dateText(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.replace('T', ' ').replace('Z', '').slice(0, 16);
  }
  // 后端统一存 UTC（带 Z），这里换成本地时区（研究组在 UTC+8 办公）
  return date.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-');
}

export function duration(ms: number | null | undefined): string {
  if (!ms) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function confidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}
