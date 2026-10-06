"use client";

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

type DrawerProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  dirty?: boolean;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
};

export default function Drawer({ open, onClose, title, subtitle, dirty, children, footer, width = 430 }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [confirmClose, setConfirmClose] = useState(false);

  const requestClose = useCallback(() => {
    if (dirty) { setConfirmClose(true); return; }
    onClose();
  }, [dirty, onClose]);

  useEffect(() => {
    if (!open) { setConfirmClose(false); return; }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") requestClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, requestClose]);

  // Focus trap: keep Tab cycling inside the drawer
  useEffect(() => {
    if (!open || !panelRef.current) return;
    const panel = panelRef.current;
    const focusable = () => panel.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])');
    const first = focusable()[0];
    first?.focus();

    function trap(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
      const nodes = focusable();
      if (nodes.length === 0) return;
      const firstEl = nodes[0];
      const lastEl = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
    }
    panel.addEventListener("keydown", trap);
    return () => panel.removeEventListener("keydown", trap);
  }, [open]);

  if (!open) return null;

  return (
    <div className="drawer-scrim" onClick={requestClose}>
      <aside
        ref={panelRef}
        className="drawer-panel"
        style={{ width: `min(${width}px, 100%)` }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <button className="drawer-close" onClick={requestClose} aria-label="Close" type="button">&times;</button>
        {subtitle && <p className="eyebrow">{subtitle}</p>}
        <h2 className="drawer-title">{title}</h2>

        <div className="drawer-body">{children}</div>

        {footer && <div className="drawer-footer">{footer}</div>}

        {confirmClose && (
          <div className="drawer-confirm-overlay">
            <div className="drawer-confirm" role="alertdialog" aria-label="Unsaved changes">
              <p>You have unsaved changes. Discard them?</p>
              <div className="drawer-confirm-actions">
                <button className="button button-secondary" type="button" onClick={() => setConfirmClose(false)}>Keep editing</button>
                <button className="button button-danger" type="button" onClick={() => { setConfirmClose(false); onClose(); }}>Discard</button>
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

// Hook for simple form-dirty tracking
export function useDirty<T>(initial: T): [T, (next: T | ((prev: T) => T)) => void, boolean, () => void] {
  const [value, setValue] = useState(initial);
  const [dirty, setDirty] = useState(false);
  const set = useCallback((next: T | ((prev: T) => T)) => { setValue(next); setDirty(true); }, []);
  const reset = useCallback(() => { setDirty(false); }, []);
  return [value, set, dirty, reset];
}
