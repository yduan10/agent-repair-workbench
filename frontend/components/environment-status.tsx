"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ChevronUp, RefreshCw } from "lucide-react";
import { useEnvironmentStatus } from "./ui/environment-context";
import { useAllowNavigation } from "./ui/navigation-guard";
import { StatusDot } from "./ui/status";
import { RelativeTime } from "./ui/relative-time";

const overallLabel = { pass: "环境就绪", running: "正在运行", unknown: "部分功能不可用", fail: "本机服务未连接", neutral: "正在检查环境…" };

export default function EnvironmentStatus() {
  const env = useEnvironmentStatus();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const allow = useAllowNavigation();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || document.querySelector("dialog[open]")) return;
      event.preventDefault();
      if (root.current?.contains(document.activeElement)) trigger.current?.focus();
      setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", key); };
  }, [open]);
  return <div className="env-status" ref={root}>
    <button type="button" ref={trigger} className="env-trigger" aria-expanded={open} aria-controls="env-pop" onClick={() => setOpen(value => !value)}>
      <StatusDot tone={env.overall} />
      <span className="env-trigger-label">{overallLabel[env.overall]}</span>
      <ChevronUp size={13} aria-hidden="true" />
    </button>
    {open && <div className="env-pop" id="env-pop" role="dialog" aria-label="本机环境状态">
      <h2>本机环境</h2>
      {env.checks.map(check => <div className="env-row" key={check.key}>
        <StatusDot tone={check.tone} />
        <strong>{check.label}<span className="muted" style={{ fontWeight: 450 }}> · {check.summary}</span></strong>
        {(check.detail || check.href) && <p>{check.detail} {check.href && <Link className="link" href={check.href} onNavigate={event => { if (!allow()) event.preventDefault(); else setOpen(false); }}>{check.tone === "running" ? "查看" : "处理方法"}</Link>}</p>}
      </div>)}
      <div className="env-pop-foot">
        <span>{env.checkedAt ? <>检查于 <RelativeTime value={env.checkedAt} /></> : "尚未完成检查"}</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={env.refresh}><RefreshCw size={12} aria-hidden="true" />重新检查</button>
      </div>
    </div>}
  </div>;
}
