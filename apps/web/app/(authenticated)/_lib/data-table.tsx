"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useMemo, useState } from "react";

export type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  sortFn?: (a: T, b: T) => number;
  width?: string;
  align?: "left" | "right";
  srOnly?: boolean;
};

type SortState = { key: string; dir: "asc" | "desc" } | null;

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  skeletonRows?: number;
  emptyTitle?: string;
  emptyBody?: ReactNode;
  stickyHeader?: boolean;
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onSelectionChange?: (keys: Set<string>) => void;
  onRowClick?: (row: T) => void;
  rowHref?: (row: T) => string;
  className?: string;
};

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  skeletonRows = 5,
  emptyTitle = "No records",
  emptyBody,
  stickyHeader = true,
  selectable,
  selectedKeys,
  onSelectionChange,
  onRowClick,
  rowHref,
  className,
}: Props<T>) {
  const [sort, setSort] = useState<SortState>(null);

  const toggleSort = useCallback((col: Column<T>) => {
    if (!col.sortable) return;
    setSort((prev) => {
      if (prev?.key === col.key) {
        if (prev.dir === "asc") return { key: col.key, dir: "desc" };
        return null;
      }
      return { key: col.key, dir: "asc" };
    });
  }, []);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const fn = col.sortFn ?? ((a: T, b: T) => {
      const av = String((a as Record<string, unknown>)[col.key] ?? "");
      const bv = String((b as Record<string, unknown>)[col.key] ?? "");
      return av.localeCompare(bv);
    });
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => fn(a, b) * dir);
  }, [rows, sort, columns]);

  const allSelected = rows.length > 0 && selectedKeys?.size === rows.length;

  const toggleAll = useCallback(() => {
    if (!onSelectionChange) return;
    if (allSelected) { onSelectionChange(new Set()); return; }
    onSelectionChange(new Set(rows.map(rowKey)));
  }, [allSelected, onSelectionChange, rows, rowKey]);

  const toggleOne = useCallback((key: string) => {
    if (!onSelectionChange || !selectedKeys) return;
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key); else next.add(key);
    onSelectionChange(next);
  }, [onSelectionChange, selectedKeys]);

  const colWidths = columns.map((c) => c.width ?? "1fr");
  if (selectable) colWidths.unshift("36px");
  const gridCols = colWidths.join(" ");

  const showSkeleton = loading && rows.length === 0;
  const showEmpty = !loading && rows.length === 0;

  return (
    <div className="dt-wrap">
      <table
        className={`dt${className ? ` ${className}` : ""}`}
        style={{ gridTemplateColumns: gridCols }}
        role="table"
      >
        <thead>
          <tr>
            {selectable && (
              <th className={stickyHeader ? "dt-sticky" : ""}>
                <input
                  type="checkbox"
                  className="dt-check"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label="Select all"
                />
              </th>
            )}
            {columns.map((col) => (
              <th
                key={col.key}
                className={`${stickyHeader ? "dt-sticky" : ""}${col.srOnly ? " sr-only" : ""}`}
                style={{ textAlign: col.align }}
                aria-sort={sort?.key === col.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
                onClick={col.sortable ? () => toggleSort(col) : undefined}
              >
                {col.header}
                {col.sortable && (
                  <span className="dt-sort-icon" aria-hidden="true">
                    {sort?.key === col.key ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {showSkeleton && Array.from({ length: skeletonRows }, (_, i) => (
            <tr key={`skel-${i}`} className="dt-skel">
              {selectable && <td><span className="skeleton" style={{ width: 18, height: 18 }} /></td>}
              {columns.map((col, ci) => (
                <td key={col.key}>
                  <span className="skeleton" style={{ width: `${55 + ((ci * 17) % 30)}%`, height: 14 }} />
                </td>
              ))}
            </tr>
          ))}
          {showEmpty && (
            <tr>
              <td
                style={{ gridColumn: `1 / -1`, justifyContent: "center" }}
              >
                <div className="dashboard-empty">
                  <strong>{emptyTitle}</strong>
                  {emptyBody && <span>{emptyBody}</span>}
                </div>
              </td>
            </tr>
          )}
          {sorted.map((row) => {
            const key = rowKey(row);
            const selected = selectedKeys?.has(key);
            const clickable = !!(onRowClick || rowHref);
            return (
              <tr
                key={key}
                className={`dt-row${clickable ? " dt-clickable" : ""}${selected ? " dt-selected" : ""}`}
                onClick={onRowClick ? () => onRowClick(row) : rowHref ? undefined : undefined}
              >
                {selectable && (
                  <td>
                    <input
                      type="checkbox"
                      className="dt-check"
                      checked={selected ?? false}
                      onChange={() => toggleOne(key)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Select row ${key}`}
                    />
                  </td>
                )}
                {columns.map((col, ci) => (
                  <td key={col.key} style={{ textAlign: col.align }}>
                    {ci === 0 && rowHref ? (
                      <Link href={rowHref(row)} className="dt-row-link">{col.render(row)}</Link>
                    ) : (
                      col.render(row)
                    )}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function RowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton-row">
          <span className="skeleton" style={{ width: "40%", height: 14 }} />
          <span className="skeleton" style={{ width: "25%", height: 14 }} />
        </div>
      ))}
    </>
  );
}
