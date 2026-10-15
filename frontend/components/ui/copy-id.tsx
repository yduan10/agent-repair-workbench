"use client";
import { Copy } from "lucide-react";
import { shortId } from "../../lib/format";
import { useToast } from "./toast";

/** Shows a short monospace identifier; copies the full value. */
export function CopyId({ value, length = 8, label = "ID" }: { value: string; length?: number; label?: string }) {
  const toast = useToast();
  const copy = async (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      toast.show({ tone: "pass", message: `已复制${label}` });
    } catch {
      toast.show({ tone: "fail", message: "浏览器不允许写入剪贴板，请手动选择复制。" });
    }
  };
  return <button type="button" className="copy-id" onClick={copy} title={value} aria-label={`复制${label} ${value}`} translate="no">
    {shortId(value, length)}<Copy size={11} aria-hidden="true" />
  </button>;
}

export function CopyButton({ value, label, children, className = "btn btn-sm" }: { value: string; label: string; children?: React.ReactNode; className?: string }) {
  const toast = useToast();
  return <button type="button" className={className} aria-label={children ? undefined : `复制${label}`} onClick={async () => {
    try { await navigator.clipboard.writeText(value); toast.show({ tone: "pass", message: `已复制${label}` }); }
    catch { toast.show({ tone: "fail", message: "浏览器不允许写入剪贴板，请手动选择复制。" }); }
  }}><Copy size={13} aria-hidden="true" />{children}</button>;
}
