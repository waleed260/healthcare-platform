"use client";

import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";

type ConfirmOptions = { title?: string; message: string; confirmLabel?: string; danger?: boolean };
type ConfirmContextValue = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    setOptions(opts);
    return new Promise<boolean>((resolve) => { resolveRef.current = resolve; });
  }, []);

  const answer = useCallback((value: boolean) => {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setOptions(null);
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options && (
        <div className="confirm-scrim" onClick={() => answer(false)}>
          <div className="confirm-dialog" role="alertdialog" aria-label={options.title ?? "Confirm"} onClick={(e) => e.stopPropagation()}>
            {options.title && <h3 className="confirm-title">{options.title}</h3>}
            <p className="confirm-message">{options.message}</p>
            <div className="confirm-buttons">
              <button className="button button-secondary" type="button" onClick={() => answer(false)}>Cancel</button>
              <button className={`button ${options.danger ? "button-danger" : "button-primary"}`} type="button" onClick={() => answer(true)}>{options.confirmLabel ?? "Confirm"}</button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmContextValue {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used inside ConfirmProvider");
  return ctx;
}
