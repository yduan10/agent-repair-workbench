"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

type ConfirmOptions = { title: string; message?: string; confirmLabel: string; cancelLabel?: string; danger?: boolean };
type ConfirmApi = (options: ConfirmOptions) => Promise<boolean>;
const ConfirmContext = createContext<ConfirmApi>(async () => false);

/** Native <dialog> confirmation; replaces window.confirm across the app. */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const confirm = useCallback<ConfirmApi>((next) => new Promise(resolve => {
    resolver.current?.(false);
    resolver.current = resolve;
    setOptions(next);
    requestAnimationFrame(() => dialog.current?.showModal());
  }), []);
  const close = useCallback((value: boolean) => {
    dialog.current?.close();
    resolver.current?.(value);
    resolver.current = null;
  }, []);
  // A confirmation belongs to the page that asked; leaving it (e.g. browser back) cancels it.
  const pathname = usePathname();
  useEffect(() => { if (resolver.current) close(false); }, [pathname, close]);
  return <ConfirmContext.Provider value={confirm}>
    {children}
    <dialog ref={dialog} className="dialog" aria-labelledby="confirm-title" onCancel={event => { event.preventDefault(); close(false); }}>
      {options && <form method="dialog" onSubmit={event => { event.preventDefault(); close(true); }}>
        <div className="dialog-body">
          <h2 id="confirm-title">{options.title}</h2>
          {options.message && <p>{options.message}</p>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={() => close(false)} autoFocus>{options.cancelLabel ?? "取消"}</button>
          <button type="submit" className={`btn btn-primary ${options.danger ? "btn-danger" : ""}`}>{options.confirmLabel}</button>
        </div>
      </form>}
    </dialog>
  </ConfirmContext.Provider>;
}
export function useConfirm() {
  return useContext(ConfirmContext);
}
