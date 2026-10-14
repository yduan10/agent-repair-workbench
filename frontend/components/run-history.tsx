"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, Clock3, Layers3, RefreshCw, Search } from "lucide-react";
import Sidebar from "./sidebar";
import WorkspaceFooter from "./workspace-footer";
import ModuleProgress from "./module-progress";
import ReproductionPanel from "./reproduction-panel";
import RunDetailView, { activeStatus, runDate } from "./run-detail";
import { capabilities } from "../lib/capabilities";
import { loadRun, loadRuns, RunDetail, runError, runStatusLabels, scenarioLabels, RunView } from "../lib/runs";
import { ReproductionCatalog } from "../lib/reproductions";

export default function RunHistory() {
  const [runs, setRuns] = useState<RunView[]>([]);
  const [refresh, setRefresh] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [catalog, setCatalog] = useState<ReproductionCatalog | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const selected = useRef<string | null>(null);
  const selectionVersion = useRef(0);
  const submitSelectionVersion = useRef(0);
  const select = useCallback((id: string) => {
    if (selected.current === id) return;
    selected.current = id; selectionVersion.current++;
    setDetail(null); setDetailError(""); setSelectedId(id);
  }, []);
  useEffect(() => {
    const readSelection = () => {
      const id = new URLSearchParams(window.location.search).get("run");
      if (id && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id)) select(id);
    };
    readSelection(); window.addEventListener("popstate", readSelection);
    return () => window.removeEventListener("popstate", readSelection);
  }, [select]);
  const onBegin = useCallback(() => { submitSelectionVersion.current = selectionVersion.current; }, []);
  const onAccepted = useCallback((id: string, choose: boolean) => {
    if (choose && submitSelectionVersion.current === selectionVersion.current) select(id);
    setRefresh(value => value + 1);
  }, [select]);
  const reload = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true); setListError("");
    loadRuns(controller.signal).then(items => {
      if (controller.signal.aborted) return;
      setRuns(items); setLoaded(true);
    }).catch(error => { if (!controller.signal.aborted) setListError(runError(error)); })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setDetailError(""); setDetailLoading(true);
    async function read() {
      try {
        const value = await loadRun(selectedId!, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value); setDetailError("");
        setRuns(items => items.map(item => item.run_id === value.run.run_id ? value.run : item));
        if (activeStatus(value.run.status)) timer = setTimeout(() => void read(), 2000);
      } catch (error) { if (!controller.signal.aborted) setDetailError(runError(error)); }
      finally { if (!controller.signal.aborted) setDetailLoading(false); }
    }
    void read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [selectedId, refresh]);
  const current = detail?.run.run_id === selectedId ? detail : null;
  const visible = runs.filter(run => (!filter || run.status === filter) && `${scenarioLabels[run.scenario]} ${run.scenario} ${run.run_id}`.toLowerCase().includes(search.toLowerCase().trim()));
  return <div className="shell"><a className="skip" href="#main">跳至运行记录</a><Sidebar />
    <main id="main"><header className="topbar"><div className="breadcrumb"><Layers3 size={16} aria-hidden="true" /><span>工作区</span><ChevronRight size={13} aria-hidden="true" /><strong>任务总览</strong></div><span className="preview-status"><span />{capabilities.tasks.label}</span></header>
      <div className="main-content module-content reproduction-content">
        <section className="intro"><div><h1>让一次调用，给出可核对的结果。</h1><p>在本机运行固定场景，观察实际状态，核验报告。已有 CLI 记录也保留在这里。</p></div></section>
        <ReproductionPanel refresh={refresh} onCatalog={setCatalog} onBegin={onBegin} onAccepted={onAccepted} onSelect={select} />
        <section className="run-history" aria-label="运行记录"><div className="run-toolbar"><div><h2>运行与结果</h2><p>当前记录来自已审核的合成故障场景，执行与状态是真实记录。</p></div><button className="download" onClick={reload} disabled={listLoading || detailLoading}><RefreshCw size={14} aria-hidden="true" />{listLoading ? "刷新中…" : "刷新记录"}</button></div>
          {listError && <div className="run-error" role="alert"><p>{listError}{loaded ? " 下方保留上次成功读取的列表，可能已过时。" : ""}</p><button className="text-link" onClick={reload}>重试读取列表</button></div>}
          <div className="run-columns"><section className="run-detail" aria-label="运行详情" aria-busy={detailLoading}>
            {detailError && <div className="run-error" role="alert"><p>{detailError}{current ? " 当前内容为上次记录，自动读取已暂停。" : ""}</p><button className="text-link" onClick={reload}>重试读取详情</button></div>}
            {!selectedId ? <div className="run-placeholder"><h3>选择一次运行</h3><p>新建复现，或从历史中选择一次运行。刷新列表会保留你的选择。</p></div> : current ? <RunDetailView key={current.run.run_id} detail={current} cancellable={catalog?.active_run_id === current.run.run_id} onChanged={reload} refreshKey={refresh} /> : detailLoading ? <p className="run-placeholder" role="status">正在读取运行详情…</p> : null}
          </section><div className="run-list-panel" aria-busy={listLoading}><h3>最近的运行</h3><p className="run-note">最近 50 条，按创建时间排列。</p>
            <div className="run-filters"><label><span><Search size={13} aria-hidden="true" />搜索记录</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="场景名称或 ID" maxLength={100} /></label><label><span>状态筛选</span><select value={filter} onChange={event => setFilter(event.target.value)}><option value="">全部状态</option>{Object.entries(runStatusLabels).map(([state, name]) => <option key={state} value={state}>{name}</option>)}</select></label></div>
            {listLoading && !loaded ? <p className="run-placeholder" role="status">正在读取运行记录…</p> : runs.length ? visible.length ? <ul className="run-list" aria-label="最近运行列表">{visible.map(run => <li key={run.run_id}><button className={`run-item ${run.run_id === selectedId ? "selected" : ""}`} aria-label={`查看运行 ${run.run_id}`} aria-pressed={run.run_id === selectedId} onClick={() => select(run.run_id)}><span className="run-item-top"><strong>{scenarioLabels[run.scenario]}</strong><span className={`run-status ${run.status}`}>{runStatusLabels[run.status]}</span></span><time dateTime={new Date(run.created_at * 1000).toISOString()}>{runDate(run.created_at)}</time></button></li>)}</ul> : <p className="run-placeholder" role="status">没有符合筛选条件的记录。</p> : !listError ? <div className="run-placeholder"><Clock3 size={26} aria-hidden="true" /><h3>还没有运行记录</h3><p>从上方新建受控复现，或从项目 CLI 使用 sandbox-check 开始记录。已有历史执行不会自动补录。</p></div> : <p className="run-placeholder">列表暂不可用，请重试读取。</p>}
          </div></div>
        </section><details className="reproduction-progress"><summary>当前能力与后续计划</summary><ModuleProgress section="tasks" /></details><WorkspaceFooter />
      </div>
    </main></div>;
}
