"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { Terminal } from "lucide-react";
import { formatDateTime, formatTime } from "../lib/format";

/** One log line. `at` is epoch milliseconds; `source` is a short actor tag (role, tool). */
export type TerminalEntry = { id: string; at: number; source?: string; message: string; level?: "error" | "notice" };
type Props = {
  /** Collapsed: a single idle line. Expanded: header, live log and auto-scroll toggle. */
  expanded: boolean;
  idle: ReactNode;
  heading?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  entries: TerminalEntry[];
  empty?: ReactNode;
};

export default function ExecutionTerminal({ expanded, idle, heading, meta, actions, entries, empty = "开始后，事件会显示在这里。" }: Props) {
  const viewport = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const seen = useRef<Set<string> | null>(null);
  const lastId = entries.at(-1)?.id;
  useEffect(() => { if (expanded && follow && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight; }, [lastId, follow, expanded]);
  // Rows that arrive after the first paint get a one-shot highlight.
  const known = seen.current;
  useEffect(() => { seen.current = new Set(entries.map(entry => entry.id)); }, [entries]);
  if (!expanded) return <section className="term term-idle" aria-label="执行控制台">
    <Terminal size={14} aria-hidden="true" /><span className="term-idle-title">执行控制台</span><span className="term-idle-text">{idle}</span>
  </section>;
  return <section className="term" aria-label="执行控制台">
    <header className="term-head">
      <div className="term-heading"><Terminal size={14} aria-hidden="true" />{heading}</div>
      {meta && <div className="term-meta">{meta}</div>}
      {actions && <div className="term-actions">{actions}</div>}
    </header>
    <div ref={viewport} className="term-log" role="region" aria-label="实时执行事件" tabIndex={0}>
      {entries.length ? <ol>{entries.map(entry => <li key={entry.id} className={known && !known.has(entry.id) ? "flash" : undefined} data-level={entry.level}>
        <time dateTime={new Date(entry.at).toISOString()} title={formatDateTime(entry.at)}>{formatTime(entry.at)}</time>
        <span className="term-source">{entry.source ?? ""}</span>
        <span className="term-message">{entry.message}</span>
      </li>)}</ol> : <p className="term-empty">{empty}</p>}
    </div>
    <footer className="term-foot">
      <label><input type="checkbox" checked={follow} onChange={event => setFollow(event.target.checked)} />自动滚动</label>
      <span className="tabular">{entries.length} 条事件</span>
    </footer>
  </section>;
}
