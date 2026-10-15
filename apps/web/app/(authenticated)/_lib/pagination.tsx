"use client";

import { useCallback, useState } from "react";

type PaginationProps = {
  hasMore: boolean;
  loading: boolean;
  error?: string | null;
  total?: number;
  onLoadMore: () => void;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
  // Screen-reader-friendly label for the Load more button (default: "Load more").
  loadMoreLabel?: string;
};

const PAGE_SIZES = [25, 50, 100];

export default function Pagination({ hasMore, loading, error, total, onLoadMore, pageSize, onPageSizeChange, loadMoreLabel = "Load more" }: PaginationProps) {
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
      {error && (
        <div className="workspace-alert" role="alert">
          <strong>{error}</strong>
          <button className="ghost-button" type="button" onClick={onLoadMore}>Retry <span>↻</span></button>
        </div>
      )}
      {hasMore && !error && (
        <button className="button button-secondary" type="button" aria-label={loadMoreLabel} onClick={onLoadMore} disabled={loading}>
          {loading ? "Loading…" : loadMoreLabel} <span>↓</span>
        </button>
      )}
    </div>
  );
}

export function usePagination<T>(fetcher: (cursor: string | null, limit: number) => Promise<{ data: T[]; nextCursor: string | null }>) {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(50);

  const load = useCallback(async (reset = false) => {
    setLoading(true);
    setError(null);
    try {
      const c = reset ? null : cursor;
      const result = await fetcher(c, pageSize);
      setItems((prev) => reset ? result.data : [...prev, ...result.data]);
      setCursor(result.nextCursor);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to load more records.");
    } finally {
      setLoading(false);
    }
  }, [cursor, fetcher, pageSize]);

  const reload = useCallback(() => {
    setCursor(null);
    return load(true);
  }, [load]);

  const changePageSize = useCallback((size: number) => {
    setPageSize(size);
    setCursor(null);
    void load(true);
  }, [load]);

  return { items, loading, hasMore: cursor !== null, error, load, reload, pageSize, changePageSize };
}
