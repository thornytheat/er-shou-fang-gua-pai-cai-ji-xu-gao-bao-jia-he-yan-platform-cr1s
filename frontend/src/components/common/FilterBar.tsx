export default function FilterBar({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div className="filters">
      {children}
      {right ? <div style={{ marginLeft: 'auto' }}>{right}</div> : null}
    </div>
  );
}
