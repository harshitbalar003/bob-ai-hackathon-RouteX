import React, { useState, useCallback } from 'react';

export type SortDir = 'asc' | 'desc';

export interface ColumnDef<T> {
  key: string;
  header: string;
  sortable?: boolean;
  numeric?: boolean; // right-aligns value; left-aligns header
  render: (row: T) => React.ReactNode;
  className?: string;
}

interface TableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  caption?: string;
  stickyHeader?: boolean;
}

interface SortState {
  key: string;
  dir: SortDir;
}

export function Table<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  caption,
  stickyHeader,
}: TableProps<T>) {
  const [sort, setSort] = useState<SortState | null>(null);

  const handleSort = useCallback((key: string) => {
    setSort((prev) => {
      if (prev?.key === key) {
        return { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' };
      }
      return { key, dir: 'asc' };
    });
  }, []);

  // Client-side sort — primitive values only; rich renders stay unsorted
  const sorted = sort
    ? [...data].sort((a, b) => {
        const col = columns.find((c) => c.key === sort.key);
        if (!col) return 0;
        const va = (a as Record<string, unknown>)[sort.key];
        const vb = (b as Record<string, unknown>)[sort.key];
        let cmp = 0;
        if (typeof va === 'number' && typeof vb === 'number') cmp = va - vb;
        else if (typeof va === 'string' && typeof vb === 'string') cmp = va.localeCompare(vb);
        return sort.dir === 'asc' ? cmp : -cmp;
      })
    : data;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        {caption && (
          <caption className="sr-only">{caption}</caption>
        )}
        <thead
          className={`text-xs text-text-muted border-b border-surface-border
            ${stickyHeader ? 'sticky top-0 bg-surface-base z-10' : ''}`}
        >
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`py-2 px-3 font-medium
                  ${col.numeric ? 'text-left' : 'text-left'}
                  ${col.sortable ? 'cursor-pointer select-none hover:text-text-primary' : ''}
                  ${col.className ?? ''}`}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                aria-sort={
                  sort?.key === col.key
                    ? sort.dir === 'asc'
                      ? 'ascending'
                      : 'descending'
                    : col.sortable
                    ? 'none'
                    : undefined
                }
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {col.sortable && (
                    <span aria-hidden="true" className="text-[10px]">
                      {sort?.key === col.key
                        ? sort.dir === 'asc'
                          ? '↑'
                          : '↓'
                        : '↕'}
                    </span>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
              className={`hover:bg-surface-raised/50 transition-colors duration-75
                ${onRowClick ? 'cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-minor' : ''}`}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`py-2 px-3 text-text-primary
                    ${col.numeric ? 'text-right tabular-nums' : ''}
                    ${col.className ?? ''}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
