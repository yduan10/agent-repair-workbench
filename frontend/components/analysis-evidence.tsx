"use client";

import { createContext, ReactNode, useContext, useEffect, useRef, useState } from "react";
import { FileCode2, FileCheck2, FileJson2, X } from "lucide-react";
import { AnalysisDetail } from "../lib/analyses";
import { loadEvidence, ReadableEvidence } from "../lib/analysis-evidence";
import { RunApiError, runError } from "../lib/runs";
import { checkLabels, findingLabels } from "../lib/report";
import { Callout } from "./ui/callout";
import { PathTrail } from "./ui/path-trail";
import { Skeleton } from "./ui/skeleton";

type Ref = AnalysisDetail["summary"]["evidence_refs"][number];
type Context = { refs: Ref[]; items: ReadableEvidence[]; error: string; loading: boolean; selected: string | null; select: (id: string | null, trigger?: HTMLElement) => void; retry: () => void };
const EvidenceContext = createContext<Context | null>(null);
export function EvidenceProvider({ detail, children }: { detail: AnalysisDetail; children: ReactNode }) {
  const [items, setItems] = useState<ReadableEvidence[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  function select(id: string | null, trigger?: HTMLElement) {
    if (id !== null) { opener.current = trigger ?? null; setSelected(id); return; }
    setSelected(null);
    const previous = opener.current;
    requestAnimationFrame(() => {
      if (previous?.isConnected) previous.focus();
      else document.querySelector<HTMLElement>(".ev-library .ev-chip")?.focus();
    });
  }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(""); setItems([]);
    let timer: ReturnType<typeof setTimeout> | undefined;
    let retries = 0;
    async function read() {
      try {
        const value = await loadEvidence(detail, controller.signal);
        if (!controller.signal.aborted) { setItems(value); setLoading(false); }
      } catch (error) {
        if (!controller.signal.aborted) {
          if (error instanceof RunApiError && error.status === 429 && retries++ < 5) timer = setTimeout(() => void read(), 1000);
          else { setError(runError(error)); setLoading(false); }
        }
      }
    }
    void read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [detail.summary.task_id, detail.sha256, refresh]);
  return <EvidenceContext.Provider value={{ refs: detail.summary.evidence_refs, items, error, loading, selected, select, retry: () => setRefresh(v => v + 1) }}>{children}</EvidenceContext.Provider>;
}
export function EvidenceReferences({ refs }: { refs: Ref[] }) {
  const context = useContext(EvidenceContext);
  if (!context || !refs.length) return null;
  return <span className="ev-chips">{refs.map(ref => {
    const item = context.items.find(v => v.ref.evidence_id === ref.evidence_id);
    const index = context.refs.findIndex(v => v.evidence_id === ref.evidence_id);
    const Icon = item?.kind === "source" ? FileCode2 : item?.kind === "contract" ? FileJson2 : FileCheck2;
    return <button type="button" key={ref.evidence_id} className="ev-chip" aria-pressed={context.selected === ref.evidence_id} onClick={event => { context.select(ref.evidence_id, event.currentTarget); requestAnimationFrame(() => { document.getElementById("evidence-reader-title")?.focus(); document.getElementById("evidence-reader")?.scrollIntoView({ block: "nearest" }); }); }}><Icon size={13} aria-hidden="true" />{item?.title ?? `证据 ${index + 1}`}</button>;
  })}</span>;
}
const checks = checkLabels;
export function EvidenceLibrary() {
  const context = useContext(EvidenceContext);
  if (!context) return null;
  const item = context.items.find(v => v.ref.evidence_id === context.selected);
  const selectedRef = context.refs.find(v => v.evidence_id === context.selected);
  return <section className="an-block ev-library" aria-label="证据">
    <h3 id="evidence-library-title" className="an-block-title">证据<span className="count tabular">{context.refs.length}</span></h3>
    {context.refs.length ? <EvidenceReferences refs={context.refs} /> : <p className="muted small">这次分析没有引用证据。</p>}
    {context.selected && <div id="evidence-reader" className="ev-reader">
      <header><h4 id="evidence-reader-title" tabIndex={-1}>{item?.title ?? "证据内容"}</h4><button type="button" className="btn btn-ghost btn-sm btn-icon" aria-label="收起证据内容" onClick={() => context.select(null)}><X size={15} aria-hidden="true" /></button></header>
      {context.loading ? <div className="ev-reader-loading" role="status" aria-busy="true"><span className="sr-only">正在读取证据…</span><Skeleton width="70%" /><Skeleton width="45%" /></div>
        : context.error ? <Callout tone="fail" role="alert" actions={<button type="button" className="btn btn-sm" onClick={context.retry}>重试</button>}>{context.error}</Callout>
        : item && <>
        <p className="muted">{item.description}</p>
        {item.report && <dl className="ev-checks"><div><dt>调用参数</dt><dd data-check={item.report.input}>{checks[item.report.input]}</dd></div><div><dt>返回结果</dt><dd data-check={item.report.output}>{checks[item.report.output]}</dd></div></dl>}
        {item.findings.length > 0 && <ul className="ev-findings">{item.findings.map((finding, i) => <li key={i}>
          <strong>{findingLabels[finding.code]?.[0] ?? "不符合项"}</strong>
          <span className="ev-finding-path"><span className="subtle small">字段路径</span><PathTrail pointer={finding.path} label="字段路径" /></span>
          <span className="subtle small">规则 <code translate="no">{finding.code}</code></span>
        </li>)}</ul>}
        {item.source && <><p className="ev-location"><code translate="no">{item.source.path}</code> · 第 {item.source.start_line}–{item.source.end_line} 行</p><pre className="ev-code" tabIndex={0} aria-label="已核对的源码片段" translate="no"><code>{item.source.text}</code></pre></>}
        {item.schemas && <div className="ev-schema"><h5><code translate="no">{item.schemas.tool_name}</code> 的契约</h5><div>
          <section><h6>参数</h6><pre className="ev-code" tabIndex={0} aria-label="输入契约" translate="no"><code>{JSON.stringify(item.schemas.input_schema, null, 2)}</code></pre></section>
          <section><h6>返回结果</h6><pre className="ev-code" tabIndex={0} aria-label="返回契约" translate="no"><code>{item.schemas.output_schema ? JSON.stringify(item.schemas.output_schema, null, 2) : "未声明"}</code></pre></section>
        </div></div>}
      </>}
      {selectedRef && <details className="an-tech ev-tech"><summary>技术详情</summary><dl className="meta-list">
        <dt>证据 ID</dt><dd><code translate="no">{selectedRef.evidence_id}</code></dd>
        <dt>SHA-256</dt><dd><code translate="no">{selectedRef.sha256}</code></dd>
      </dl></details>}
    </div>}
  </section>;
}
