"use client";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";

type ToastInput = { message: string; tone?: "pass" | "fail" | "neutral"; action?: { label: string; onClick: () => void }; duration?: number };
type ToastItem = ToastInput & { id: number };
type ToastApi = { show: (toast: ToastInput) => void };

const ToastContext = createContext<ToastApi>({ show: () => {} });
const icons = { pass: CheckCircle2, fail: XCircle, neutral: Info };

/** One polite live region for transient feedback (copy, start, stop, download). */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(0);
  const dismiss = useCallback((id: number) => setItems(list => list.filter(item => item.id !== id)), []);
  const show = useCallback((toast: ToastInput) => {
    const id = ++next.current;
    setItems(list => [...list.slice(-2), { ...toast, id }]);
    window.setTimeout(() => dismiss(id), toast.duration ?? (toast.action ? 8000 : 3200));
  }, [dismiss]);
  const api = useMemo(() => ({ show }), [show]);
  return <ToastContext.Provider value={api}>
    {children}
    <div className="toast-region" role="status" aria-live="polite">
      {items.map(item => {
        const Icon = icons[item.tone ?? "neutral"];
        return <div className="toast" data-tone={item.tone} key={item.id}>
          <Icon size={15} aria-hidden="true" />
          <p>{item.message}</p>
          {item.action && <button type="button" className="link" onClick={() => { item.action?.onClick(); dismiss(item.id); }}>{item.action.label}</button>}
          <button type="button" onClick={() => dismiss(item.id)} aria-label="关闭提示"><X size={14} aria-hidden="true" /></button>
        </div>;
      })}
    </div>
  </ToastContext.Provider>;
}
export function useToast() {
  return useContext(ToastContext);
}
