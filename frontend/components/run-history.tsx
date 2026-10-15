"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Inbox, RefreshCw, Search, SearchX } from "lucide-react";
import ReproductionPanel from "./reproduction-panel";
import RunDetailView, { RunDetailSkeleton, type StopState } from "./run-detail";
import CapabilityBadge from "./capability-badge";
import { PageHeader } from "./ui/page-header";
import { Callout } from "./ui/callout";
import { CopyId } from "./ui/copy-id";
import { EmptyState } from "./ui/empty-state";
import { RelativeTime } from "./ui/relative-time";
import { Skeleton } from "./ui/skeleton";
import { StatusBadge } from "./ui/status";
import { useConfirm } from "./ui/confirm-dialog";
import { useToast } from "./ui/toast";
import { activeStatus, loadRun, loadRuns, pollDelay, RunDetail, runDurationMs, runError, runStatusLabels, RunView, scenarioLabels } from "../lib/runs";
import { cancelReproduction, ReproductionCatalog } from "../lib/reproductions";
import { requestEnvironmentRefresh } from "../lib/environment";
import { modules } from "../lib/modules";
import { formatDuration } from "../lib/format";
import { runTone } from "../lib/tones";

const UUID = /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
type Status = RunView["status"];
const isStatus = (value: string | null): value is Status => !!value && Object.hasOwn(runStatusLabels, value);

function Header({ onRefresh, busy }: { onRefresh?: () => void; busy?: boolean }) {
  return <PageHeader title={modules.tasks.title} description={modules.tasks.description} badge={<CapabilityBadge section="tasks" />}
    actions={<button type="button" className="btn btn-sm" onClick={onRefresh} disabled={!onRefresh || busy} aria-busy={busy || undefined}>
      <RefreshCw size={13} aria-hidden="true" />{busy ? "刷新中…" : "刷新"}
    </button>} />;
}

function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return <div className="run-rows-skeleton" role="status" aria-busy="true">
    <span className="sr-only">正在读取运行记录…</span>
    {Array.from({ length: rows }, (_, index) => <div key={index}>
      <span><Skeleton width={72 + (index % 3) * 12} height={13} /><Skeleton width={64} height={10} /></span>
      <Skeleton width={64} height={20} /><Skeleton width={40} height={11} /><Skeleton width={52} height={11} />
    </div>)}
  </div>;
}

function Fallback() {
  return <>
    <Header />
    <div className="launcher launcher-skeleton" aria-hidden="true"><Skeleton width={360} height={32} /><Skeleton width="50%" height={11} /></div>
    <div className="run-workspace"><div className="pane run-list-pane"><ListSkeleton /></div><div className="pane run-detail-pane"><RunDetailSkeleton /></div></div>
  </>;
}

export default function RunHistory() {
  return <Suspense fallback={<Fallback />}><RunWorkspace /></Suspense>;
}

function RunWorkspace() {
  const params = useSearchParams();
  const confirm = useConfirm();
  const toast = useToast();
  const urlRun = params.get("run");
  const explicit = urlRun && UUID.test(urlRun) ? urlRun : null;
  const [search, setSearch] = useState(() => (params.get("q") ?? "").slice(0, 100));
  const [statusFilter, setStatusFilter] = useState<Status | "">(() => { const value = params.get("status"); return isStatus(value) ? value : ""; });
  const [runs, setRuns] = useState<RunView[]>([]);
  const [refresh, setRefresh] = useState(0);
  const [listVersion, setListVersion] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [catalog, setCatalog] = useState<ReproductionCatalog | null>(null);
  const [stopping, setStopping] = useState<Record<string, StopState>>({});
  // Stop requests whose outcome could not be confirmed; shown on the active-run bar until that run ends.
  const [stopUnknown, setStopUnknown] = useState<Record<string, true>>({});
  const selectionVersion = useRef(0);
  const submitSelectionVersion = useRef(0);
  const stopGuard = useRef(new Set<string>());
  const stopRequests = useRef(new Set<AbortController>());
  const lastActive = useRef<string | null>(null);
  const tableRef = useRef<HTMLTableSectionElement>(null);
  const detailRef = useRef<HTMLElement>(null);

  const query = search.toLowerCase().trim();
  const visible = useMemo(() => runs.filter(run => (!statusFilter || run.status === statusFilter)
    && `${scenarioLabels[run.scenario]} ${run.scenario} ${run.run_id}`.toLowerCase().includes(query)), [runs, statusFilter, query]);
  // Newest record is selected when the URL names none, so the page never opens on an empty detail.
  const selectedId = explicit ?? visible[0]?.run_id ?? null;

  const writeParams = useCallback((changes: Record<string, string | null>, mode: "push" | "replace") => {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(changes)) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); }
    url.hash = "";
    if (url.href === window.location.href) return;
    window.history[mode === "push" ? "pushState" : "replaceState"](null, "", url);
  }, []);
  const hrefFor = useCallback((id: string) => {
    const next = new URLSearchParams(params.toString()); next.set("run", id);
    return `?${next.toString()}`;
  }, [params]);
  const select = useCallback((id: string, mode: "push" | "replace" = "push") => {
    selectionVersion.current++;
    writeParams({ run: id }, mode);
  }, [writeParams]);
  // Back/forward is a user choice too: resync the filters from the URL and let it win over a late submit response.
  useEffect(() => {
    const sync = () => {
      const url = new URL(window.location.href);
      const q = (url.searchParams.get("q") ?? "").slice(0, 100);
      const state = url.searchParams.get("status");
      selectionVersion.current++;
      setSearch(value => (value.trim() ? value : "") === q ? value : q);
      setStatusFilter(isStatus(state) ? state : "");
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  // Pin the automatically chosen newest record in the URL so refreshing, filtering or sharing keeps showing it.
  const autoId = !explicit && loaded ? visible[0]?.run_id ?? null : null;
  useEffect(() => { if (autoId) writeParams({ run: autoId }, "replace"); }, [autoId, writeParams]);
  const openFromList = useCallback((id: string) => {
    select(id);
    if (window.matchMedia("(max-width: 900px)").matches) requestAnimationFrame(() => detailRef.current?.scrollIntoView({ block: "start" }));
  }, [select]);

  const reload = useCallback(() => setRefresh(value => value + 1), []);
  const onBegin = useCallback(() => { submitSelectionVersion.current = selectionVersion.current; }, []);
  const onAccepted = useCallback((id: string, choose: boolean) => {
    // A late response must not override a record the user picked while the request was in flight.
    if (choose && submitSelectionVersion.current === selectionVersion.current) select(id);
    setListVersion(value => value + 1);
  }, [select]);
  const onCatalog = useCallback((value: ReproductionCatalog | null) => {
    setCatalog(value);
    const active = value?.active_run_id ?? null;
    if (lastActive.current && lastActive.current !== active) setListVersion(version => version + 1);
    lastActive.current = active;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true); setListError("");
    loadRuns(controller.signal).then(items => {
      if (controller.signal.aborted) return;
      setRuns(items); setLoaded(true);
    }).catch(error => { if (!controller.signal.aborted) setListError(runError(error)); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [refresh, listVersion]);

  useEffect(() => {
    if (!selectedId) return;
    const id = selectedId;
    const controller = new AbortController();
    setDetailError(""); setDetailLoading(true);
    async function read() {
      try {
        const value = await loadRun(id, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value); setDetailError(""); setDetailLoading(false);
        setRuns(items => items.map(item => item.run_id === value.run.run_id ? value.run : item));
        // Poll only while the run is active; pause while the tab is hidden.
        if (activeStatus(value.run.status)) { await pollDelay(2000, controller.signal); if (!controller.signal.aborted) void read(); }
      } catch (error) {
        if (!controller.signal.aborted) { setDetailError(runError(error)); setDetailLoading(false); }
      }
    }
    void read();
    return () => controller.abort();
  }, [selectedId, refresh]);

  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; stopRequests.current.forEach(controller => controller.abort()); }; }, []);

  const stop = useCallback(async (id: string) => {
    if (stopGuard.current.has(id)) return;
    stopGuard.current.add(id);
    try {
      const ok = await confirm({ title: "停止这次复现？", message: "将请求停止容器并清理，清理结果以运行报告为准。已经发给工具的调用可能仍会完成，这条运行会记录为已停止或结果未知。", confirmLabel: "停止运行", danger: true });
      // The page may have been left while the dialog was open; never send a stop from an unmounted page.
      if (!ok || !mounted.current) return;
      setStopping(value => ({ ...value, [id]: "sending" }));
      setStopUnknown(({ [id]: _previous, ...rest }) => rest);
      // The stop button is disabled while sending, so the dialog cannot hand focus back to it; keep keyboard users on the run bar.
      requestAnimationFrame(() => {
        const focused = document.activeElement as HTMLButtonElement | null;
        if (!focused || focused === document.body || focused.disabled) document.getElementById("launcher-active")?.focus();
      });
      const controller = new AbortController(); stopRequests.current.add(controller);
      try {
        const result = await cancelReproduction(id, controller.signal);
        if (controller.signal.aborted) return;
        if (result.status === "cancel_requested") {
          setStopping(value => ({ ...value, [id]: "requested" }));
          toast.show({ message: "已请求停止，正在等待容器清理。" });
        } else {
          setStopping(({ [id]: _done, ...rest }) => rest);
          toast.show({ message: "运行已经结束，正在刷新结果。" });
        }
      } catch {
        if (controller.signal.aborted) return;
        setStopping(({ [id]: _failed, ...rest }) => rest);
        setStopUnknown(value => ({ ...value, [id]: true }));
      } finally { stopRequests.current.delete(controller); }
      reload(); requestEnvironmentRefresh();
    } finally { stopGuard.current.delete(id); }
  }, [confirm, toast, reload]);

  const updateSearch = (value: string) => { setSearch(value); writeParams({ q: value.trim() ? value : null }, "replace"); };
  const updateStatus = (value: string) => { const next = isStatus(value) ? value : ""; setStatusFilter(next); writeParams({ status: next || null }, "replace"); };
  const clearFilters = () => { setSearch(""); setStatusFilter(""); writeParams({ q: null, status: null }, "replace"); };

  const onListKey = (event: React.KeyboardEvent) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    if (!visible.length || event.altKey || event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    const index = visible.findIndex(run => run.run_id === selectedId);
    const next = Math.min(visible.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1)));
    const id = visible[next].run_id;
    select(id, "replace");
    tableRef.current?.querySelector<HTMLElement>(`tr[data-run-id="${id}"] a`)?.focus();
  };

  const current = detail?.run.run_id === selectedId ? detail : null;
  const activeId = catalog?.active_run_id ?? null;
  const activeRun = (activeId && (runs.find(run => run.run_id === activeId) ?? (current?.run.run_id === activeId ? current.run : null))) || null;
  const filtered = !!(query || statusFilter);
  const showDetail = !!selectedId;

  return <>
    <Header onRefresh={reload} busy={listLoading && loaded} />
    <ReproductionPanel refresh={refresh} onCatalog={onCatalog} onBegin={onBegin} onAccepted={onAccepted}
      activeRun={activeRun} runHref={hrefFor} onOpenRun={openFromList} stopState={activeId ? stopping[activeId] : undefined}
      stopUnknown={!!activeId && !!stopUnknown[activeId]} onStop={id => void stop(id)} />

    <div className="run-workspace" data-single={!showDetail || undefined}>
      <section className="pane run-list-pane" id="run-list" aria-labelledby="run-list-heading" aria-busy={listLoading}>
        <div className="run-list-head">
          <h2 id="run-list-heading" tabIndex={-1}>运行记录{loaded && <span className="count tabular">{filtered ? `${visible.length} / ${runs.length}` : runs.length}</span>}</h2>
          {(!loaded || runs.length > 0) && <div className="run-list-filters">
            <label className="input-search">
              <span className="sr-only">搜索运行</span>
              <Search size={13} aria-hidden="true" />
              <input className="input" type="search" name="q" autoComplete="off" spellCheck={false} value={search} maxLength={100} placeholder="搜索场景或 ID…" onChange={event => updateSearch(event.target.value)} />
            </label>
            <label className="run-status-filter">
              <span className="sr-only">状态筛选</span>
              <select className="select" name="status" value={statusFilter} onChange={event => updateStatus(event.target.value)}>
                <option value="">全部状态</option>
                {Object.entries(runStatusLabels).map(([state, name]) => <option key={state} value={state}>{name}</option>)}
              </select>
            </label>
          </div>}
        </div>
        {listError && <div className="run-pane-note"><Callout tone="fail" title="无法读取运行记录" role="alert"
          actions={<button type="button" className="btn btn-sm" onClick={reload} disabled={listLoading}>重试</button>}>
          {listError}{loaded ? " 下方是上次读取的列表，可能已过时。" : ""}</Callout></div>}
        {listLoading && !loaded ? <ListSkeleton />
          : runs.length ? visible.length ? <div className="table-scroll"><table className="data-table run-table" onKeyDown={onListKey}>
            <caption className="sr-only">最近 50 条运行，按开始时间从新到旧排列。用上下方向键切换。</caption>
            <thead><tr><th scope="col">场景</th><th scope="col">状态</th><th scope="col" className="num hide-sm">耗时</th><th scope="col" className="num">开始</th></tr></thead>
            <tbody ref={tableRef}>{visible.map(run => {
              const selected = run.run_id === selectedId;
              const duration = runDurationMs(run);
              return <tr key={run.run_id} data-run-id={run.run_id} aria-selected={selected}>
                <td>
                  <a className="row-link" href={hrefFor(run.run_id)} aria-current={selected ? "true" : undefined}
                    onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return; event.preventDefault(); openFromList(run.run_id); }}>
                    {scenarioLabels[run.scenario]}<span className="sr-only">，{runStatusLabels[run.status]}</span>
                  </a>
                  <span className="run-row-id"><CopyId value={run.run_id} label="运行 ID" /></span>
                </td>
                <td className="nowrap"><StatusBadge tone={runTone(run.status)}>{runStatusLabels[run.status]}</StatusBadge></td>
                <td className="num subtle nowrap hide-sm">{duration === null ? "—" : formatDuration(duration)}</td>
                <td className="num subtle nowrap"><RelativeTime value={run.created_at} /></td>
              </tr>;
            })}</tbody>
          </table></div>
          : <EmptyState icon={SearchX} title="没有符合条件的运行" actions={<button type="button" className="btn btn-sm" onClick={clearFilters}>清除筛选</button>}>换个关键词或状态再试。</EmptyState>
          : !listError ? <EmptyState icon={Inbox} title="还没有运行记录">在上方选择场景，点击「开始复现」。也可以在终端运行 <code translate="no">sandbox-check</code>，结果同样会出现在这里。</EmptyState>
          : null}
        {loaded && runs.length > 0 && <p className="run-list-foot small subtle">显示最近 50 条，包括在终端发起的运行。</p>}
      </section>

      {showDetail && <section ref={detailRef} className="pane run-detail-pane" aria-label="运行详情" aria-busy={detailLoading}>
        {detailError && <div className="run-pane-note"><Callout tone="fail" title="无法读取运行详情" role={listError ? undefined : "alert"}
          actions={<button type="button" className="btn btn-sm" onClick={reload} disabled={detailLoading}>重试</button>}>
          {detailError}{current ? " 下方是上次读取的内容，已停止自动刷新。" : ""}</Callout></div>}
        {current ? <RunDetailView key={current.run.run_id} detail={current} cancellable={activeId === current.run.run_id}
          stopState={stopping[current.run.run_id]} onStop={run => void stop(run.run_id)} refreshKey={refresh} announce={!listError && !detailError} />
          : !detailError ? <RunDetailSkeleton /> : null}
      </section>}
    </div>
  </>;
}
