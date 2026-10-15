"use client";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, Inbox, RefreshCw, Search } from "lucide-react";
import AnalysisConsole from "./analysis-console";
import AnalysisView from "./analysis-detail";
import CapabilityBadge from "./capability-badge";
import { PageHeader } from "./ui/page-header";
import { StatusBadge } from "./ui/status";
import { RelativeTime } from "./ui/relative-time";
import { Skeleton, SkeletonRows } from "./ui/skeleton";
import { EmptyState } from "./ui/empty-state";
import { Callout } from "./ui/callout";
import { AnalysisDetail, SavedAnalysis, analysisStatus, intentLabels, loadAnalyses, loadAnalysis, sourceLabels } from "../lib/analyses";
import { whenVisible } from "../lib/analysis-runs";
import { RunApiError, runError } from "../lib/runs";
import { analysisTone } from "../lib/tones";
import { durationBetween, formatDuration, formatNumber, formatShortDateTime, shortId } from "../lib/format";
import { modules } from "../lib/modules";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export default function AnalysisHistory() {
  return <>
    <PageHeader title={modules.diagnosis.title} description={modules.diagnosis.description} badge={<CapabilityBadge section="diagnosis" />}
      actions={<Link className="btn btn-ghost btn-sm" href="/workspace/connections#contracts">角色与工具接口<ArrowUpRight size={13} aria-hidden="true" /></Link>} />
    <Suspense fallback={<WorkspaceSkeleton />}><AnalysisWorkspace /></Suspense>
  </>;
}

function WorkspaceSkeleton() {
  return <div className="an-skeleton" aria-busy="true">
    <div className="pane an-launch"><div className="an-launch-row"><Skeleton width={200} height={32} /><Skeleton width={200} height={32} /><Skeleton width={104} height={32} /></div></div>
    <div className="pane"><SkeletonRows rows={4} label="正在读取分析记录…" /></div>
  </div>;
}

function tokensOf({ usage }: SavedAnalysis["summary"]) {
  return usage.known_input_tokens + usage.known_output_tokens;
}

function AnalysisWorkspace() {
  const params = useSearchParams();
  const raw = params.get("analysis");
  const selected = raw && UUID.test(raw) ? raw : null;
  const [items, setItems] = useState<SavedAnalysis[]>([]);
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [detailMissing, setDetailMissing] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [cliOpen, setCliOpen] = useState(false);
  const detailRef = useRef<HTMLElement>(null);

  const selectAnalysis = useCallback((id: string, options: { replace?: boolean; reveal?: boolean } = {}) => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("analysis") === id) return;
    url.searchParams.set("analysis", id);
    if (options.replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
    if (options.reveal && window.matchMedia("(max-width: 900px)").matches) requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "start" }));
  }, []);
  const select = useCallback((id: string) => selectAnalysis(id), [selectAnalysis]);

  useEffect(() => {
    const controller = new AbortController(); setListLoading(true); setListError("");
    loadAnalyses(controller.signal).then(value => { if (!controller.signal.aborted) { setItems(value); setLoaded(true); } })
      .catch(error => { if (!controller.signal.aborted) setListError(runError(error)); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [refresh]);
  // Desktop: open the newest record when nothing is selected. Mobile keeps the list first.
  useEffect(() => {
    if (selected || !loaded || !items.length) return;
    if (window.matchMedia("(min-width: 901px)").matches) selectAnalysis(items[0].summary.task_id, { replace: true });
  }, [selected, loaded, items, selectAnalysis]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined; let cancelVisible = () => {};
    setDetailLoading(true); setDetailError(""); setDetailMissing(false);
    async function read() {
      try {
        const result = await loadAnalysis(selected!, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(result); setDetailError("");
        setItems(old => old.some(item => item.summary.task_id === selected)
          ? old.map(item => item.summary.task_id === selected ? { summary: result.summary, sha256: result.sha256 } : item)
          : [{ summary: result.summary, sha256: result.sha256 }, ...old]);
        // Poll while running; a hidden tab waits until it is visible again.
        if (result.summary.state.phase !== "finished") timer = setTimeout(() => { cancelVisible = whenVisible(() => void read()); }, 2000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setDetailError(runError(error)); setDetailMissing(error instanceof RunApiError && error.status === 404);
      }
      finally { if (!controller.signal.aborted) setDetailLoading(false); }
    }
    void read(); return () => { controller.abort(); clearTimeout(timer); cancelVisible(); };
  }, [selected, refresh]);

  const current = detail?.summary.task_id === selected ? detail : null;
  const reload = () => setRefresh(value => value + 1);
  const needle = query.trim().toLowerCase();
  const filtered = needle ? items.filter(({ summary: s }) => `${intentLabels[s.state.intent]} ${analysisStatus(s)} ${formatShortDateTime(s.started_at)} ${s.task_id}`.toLowerCase().includes(needle)) : items;
  const openCli = () => { setCliOpen(true); requestAnimationFrame(() => { const toggle = document.getElementById("analysis-cli-toggle"); toggle?.scrollIntoView({ block: "center" }); toggle?.focus(); }); };

  return <>
    <AnalysisConsole detail={current} onSelect={select} onRefresh={reload} refreshKey={refresh} cliOpen={cliOpen} onCliOpenChange={setCliOpen}
      pendingMissing={detailMissing && !!selected && selected === pendingId} onPendingChange={setPendingId} />
    <section id="analysis-results" className="section" aria-labelledby="analysis-records-heading">
      <div className="section-head">
        <h2 id="analysis-records-heading">分析记录{loaded && <span className="count tabular">{items.length}</span>}</h2>
        <button type="button" className="btn btn-ghost btn-sm" disabled={listLoading} aria-busy={listLoading || undefined} onClick={reload}><RefreshCw size={13} aria-hidden="true" />刷新</button>
      </div>
      {listError && <div className="an-alert"><Callout tone="fail" role="alert" actions={<button type="button" className="btn btn-sm" onClick={reload}>重试</button>}>{listError}{loaded ? " 下方是上次读取的列表。" : ""}</Callout></div>}
      <div className="an-columns">
        <nav className="pane an-list" aria-label="分析列表">
          {(loaded || items.length > 0) && items.length > 0 && <div className="an-list-head">
            <label className="input-search"><Search size={14} aria-hidden="true" /><span className="sr-only">搜索分析记录</span>
              <input className="input an-search" type="search" name="analysis-query" autoComplete="off" spellCheck={false} placeholder="按结果、目标、日期或 ID 筛选" value={query} onChange={event => setQuery(event.target.value)} /></label>
          </div>}
          {listLoading && !loaded ? <SkeletonRows rows={4} label="正在读取分析记录…" />
            : filtered.length ? <ul className="an-rows">{filtered.map(({ summary: s }) => {
              const active = selected === s.task_id;
              const tokens = tokensOf(s);
              return <li key={s.task_id}>
                <a href={`?analysis=${s.task_id}`} className="an-row" aria-current={active ? "true" : undefined} data-analysis-id={s.task_id}
                  onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return; event.preventDefault(); selectAnalysis(s.task_id, { reveal: true }); }}>
                  <span className="an-row-top"><strong>{intentLabels[s.state.intent]}</strong><RelativeTime value={s.started_at} /></span>
                  <span className="an-row-bottom">
                    <StatusBadge tone={analysisTone(s)}>{analysisStatus(s)}</StatusBadge>
                    <span className="an-row-meta tabular">
                      <span>{sourceLabels[s.source_kind]}</span>
                      {s.finished_at && <span>{formatDuration(durationBetween(s.started_at, s.finished_at))}</span>}
                      {s.usage.model_calls > 0 && <span>{s.usage.usage_complete ? `${formatNumber(tokens)} token` : "用量待确认"}</span>}
                    </span>
                  </span>
                  <span className="sr-only">分析 {shortId(s.task_id)}</span>
                </a>
              </li>;
            })}</ul>
            : listError && !loaded ? <p className="an-list-empty">无法读取列表，原因见上方。</p>
            : query ? <p className="an-list-empty">没有匹配的分析。<button type="button" className="link an-inline-button" onClick={() => setQuery("")}>清除筛选</button></p>
            : <EmptyState icon={Inbox} title="还没有分析记录" actions={<button type="button" className="btn btn-sm" onClick={openCli}>在终端运行</button>}>在上方选择案例和目标，点击「开始分析」。</EmptyState>}
        </nav>
        <section ref={detailRef} className="pane an-detail" aria-label="分析详情" aria-busy={detailLoading} data-empty={!selected || undefined}>
          {detailError && detailMissing && selected === pendingId ? <div className="an-alert"><Callout tone="unknown" title="还没有这次提交的记录">服务端没有找到这个请求 ID，上次提交可能没有送达。可以在上方用同一 ID 重新提交，或放弃这次提交。</Callout></div>
            : detailError && <div className="an-alert"><Callout tone="fail" role="alert" actions={<button type="button" className="btn btn-sm" onClick={reload}>重试</button>}>{detailError}{current ? " 下方是上次读取的内容，已停止自动刷新。" : ""}</Callout></div>}
          {current ? <AnalysisView key={current.summary.task_id} detail={current} />
            : selected ? !detailError && <div className="an-detail-skeleton" role="status" aria-busy="true"><span className="sr-only">正在读取分析详情…</span><Skeleton width="40%" height={20} /><Skeleton width="70%" height={13} /><Skeleton width="100%" height={64} /><Skeleton width="100%" height={40} /><Skeleton width="85%" height={13} /></div>
            : <EmptyState title={items.length ? "选择一条分析记录" : "还没有分析详情"}>{items.length ? "在列表中选择一条记录，查看各角色的结论和证据。" : "完成第一次分析后，结论和证据会显示在这里。"}</EmptyState>}
        </section>
      </div>
    </section>
  </>;
}
