"use client";

import { useCallback, useState } from "react";

type PaginationProps = {
  hasMore: boolean;
  loading: boolean;
  total?: number;
  onLoadMore: () => void;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
};

const PAGE_SIZES = [25, 50, 100];

export default function Pagination({ hasMore, loading, total, onLoadMore, pageSize, onPageSizeChange }: PaginationProps) {
  return (
    <div className="pagination-bar">
      <div className="pagination-info">
        {total !== undefined && <span className="pagination-count">{total} shown</span>}
        <label className="pagination-size">
          Per page
          <select value={pageSize} onChange={(e) => onPageSizeChange(Number(e.target.value))}>
            {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
      </div>
      {hasMore && (
        <button className="button button-secondary" type="button" onClick={onLoadMore} disabled={loading}>
          {loading ? "Loading…" : "Load more"} <span>↓</span>
        </button>
      )}
    </div>
  );
}

export function usePagination<T>(fetcher: (cursor: string | null, limit: number) => Promise<{ data: T[]; nextCursor: string | null }>) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pageSize, setPageSize] = useState(50);

  const load = useCallback(async (reset = false) => {
    setLoading(true);
    try {
      const c = reset ? null : cursor;
      const result = await fetcher(c, pageSize);
      setItems((prev) => reset ? result.data : [...prev, ...result.data]);
      setCursor(result.nextCursor);
    } finally {
      setLoading(false);
    }
  }, [cursor, fetcher, pageSize]);

  const reload = useCallback(() => {
    setCursor(null);
    setItems([]);
    return load(true);
  }, [load]);

  const changePageSize = useCallback((size: number) => {
    setPageSize(size);
    setCursor(null);
    setItems([]);
  }, []);

  return { items, loading, hasMore: cursor !== null, load, reload, pageSize, changePageSize };
}
