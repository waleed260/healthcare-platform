"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

type ToastType = "success" | "error" | "info";
type Toast = { id: number; type: ToastType; message: string };
type ToastContextValue = {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) clearTimeout(t);
    timers.current.delete(id);
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback((type: ToastType, message: string) => {
    const id = nextId++;
    setToasts((prev) => [...prev, { id, type, message }]);
    timers.current.set(id, setTimeout(() => dismiss(id), type === "error" ? 6000 : 4000));
  }, [dismiss]);

  useEffect(() => {
    return () => { timers.current.forEach((t) => clearTimeout(t)); };
  }, []);

  const value: ToastContextValue = {
    success: useCallback((m: string) => push("success", m), [push]),
    error: useCallback((m: string) => push("error", m), [push]),
    info: useCallback((m: string) => push("info", m), [push]),
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      {toasts.length > 0 && (
        <div className="toast-container" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className={`toast toast-${toast.type}`} role="status">
              <span className="toast-icon">{toast.type === "success" ? "✓" : toast.type === "error" ? "✕" : "i"}</span>
              <span className="toast-message">{toast.message}</span>
              <button className="toast-dismiss" type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss">&times;</button>
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
