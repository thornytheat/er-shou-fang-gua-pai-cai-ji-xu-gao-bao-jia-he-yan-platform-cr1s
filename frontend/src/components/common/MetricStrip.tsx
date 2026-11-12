export interface Metric {
  k: string;
  v: React.ReactNode;
  unit?: string;
  d?: string;
}

export default function MetricStrip({ items }: { items: Metric[] }) {
  return (
    <div className="metrics" data-testid="metric-strip">
      {items.map((item) => (
        <div className="metric" key={item.k}>
          <div className="k">{item.k}</div>
          <div className="v">
            {item.v}
            {item.unit ? <small>{item.unit}</small> : null}
          </div>
          {item.d ? <div className="d">{item.d}</div> : null}
        </div>
      ))}
    </div>
  );
}
