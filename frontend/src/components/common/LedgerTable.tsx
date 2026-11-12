import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  width?: string;
  render: (row: T) => ReactNode;
}

export interface LedgerTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string;
  caption?: string;
  testId?: string;
}

/** 台账式表格：虚线行、无卡片、可整行点击。挂牌池与核验队列共用。 */
export default function LedgerTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  rowClassName,
  caption,
  testId,
}: LedgerTableProps<T>) {
  return (
    <div className="ledger-wrap">
      <table className="ledger" data-testid={testId}>
        {caption ? <caption className="tiny muted" style={{ textAlign: 'left', padding: '0 0 8px' }}>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={{ textAlign: column.align || 'left', width: column.width }}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={`${onRowClick ? 'clickable' : ''} ${rowClassName ? rowClassName(row) : ''}`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} style={{ textAlign: column.align || 'left' }}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
