"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ChevronRight, Clock3, Layers3, RefreshCw } from "lucide-react";
import Sidebar from "./sidebar";
import WorkspaceFooter from "./workspace-footer";
import ModuleProgress from "./module-progress";
import { capabilities } from "../lib/capabilities";
import { eventLabels, executorLabels, loadReport, loadRun, loadRuns, RunDetail, runError, runStatusLabels, scenarioLabels, RunView } from "../lib/runs";

function date(seconds: number) {
  return new Date(seconds * 1000).toLocaleString("zh-CN", { hour12: false });
}

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
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadNotice, setDownloadNotice] = useState("");
  const downloadRequest = useRef<AbortController | null>(null);
  const selection = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    setListError("");
    loadRuns(controller.signal).then(items => {
      if (controller.signal.aborted) return;
      setRuns(items);
      setLoaded(true);
    }).catch(error => {
      if (!controller.signal.aborted) setListError(runError(error));
    }).finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    loadRun(selectedId, controller.signal).then(value => {
      if (!controller.signal.aborted) setDetail(value);
    }).catch(error => {
      if (!controller.signal.aborted) setDetailError(runError(error));
    }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selectedId, refresh]);

  useEffect(() => () => downloadRequest.current?.abort(), []);

  function select(id: string) {
    if (selectedId === id) return;
    downloadRequest.current?.abort();
    selection.current = id;
    setDownloadLoading(false);
    setDownloadNotice("");
    setDetail(null);
    setDetailError("");
    setSelectedId(id);
  }
  function reload() {
    downloadRequest.current?.abort();
    setDownloadLoading(false);
    setDownloadNotice("");
    setRefresh(value => value + 1);
  }
  async function download(run: RunView) {
    if (downloadLoading) return;
    const controller = new AbortController();
    downloadRequest.current?.abort();
    downloadRequest.current = controller;
    setDownloadLoading(true);
    setDownloadNotice("");
    try {
      const bytes = await loadReport(run, controller.signal);
      if (controller.signal.aborted || selection.current !== run.run_id) return;
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `run-${run.run_id}.json`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDownloadNotice("报告校验通过，已开始下载。");
    } catch (error) {
      if (!controller.signal.aborted) setDownloadNotice(runError(error));
    } finally {
      if (!controller.signal.aborted) setDownloadLoading(false);
    }
  }
  const current = detail?.run.run_id === selectedId ? detail : null;
  return (
    <div className="shell">
      <a className="skip" href="#main">跳至运行记录</a>
      <Sidebar />
      <main id="main">
        <header className="topbar">
          <div className="breadcrumb"><Layers3 size={16} aria-hidden="true" /><span>工作区</span><ChevronRight size={13} aria-hidden="true" /><strong>任务总览</strong></div>
          <span className="preview-status"><span />{capabilities.tasks.label}</span>
        </header>
        <div className="main-content module-content">
          <section className="intro"><div><div className="intro-label">本地运行记录</div><h1>每次运行，都有记录可查。</h1><p>查看 CLI 留下的真实状态、事件与报告。本页只读，不发起、取消或重试执行。</p></div></section>
          <ModuleProgress section="tasks" />
          <section className="run-history" aria-label="运行记录">
            <div className="run-toolbar">
              <div><h2>最近的运行</h2><p>最多显示最近 50 条，按创建时间从新到旧排列。</p><p>当前记录来自已审核的合成故障场景，执行与状态是真实记录。</p></div>
              <button className="download" onClick={reload} disabled={listLoading || detailLoading}><RefreshCw size={14} aria-hidden="true" />{listLoading ? "刷新中…" : "刷新记录"}</button>
            </div>
            {listError && <div className="run-error" role="alert"><p>{listError}{loaded ? " 下方保留上次成功读取的列表，可能已过时。" : ""}</p><button className="text-link" onClick={reload}>重试读取列表</button></div>}
            <div className="run-columns">
              <div className="run-list-panel" aria-busy={listLoading}>
                {listLoading && !loaded ? <p className="run-placeholder" role="status">正在读取运行记录…</p> : runs.length ? (
                  <ul className="run-list" aria-label="最近运行列表">
                    {runs.map(run => <li key={run.run_id}><button className={`run-item ${run.run_id === selectedId ? "selected" : ""}`} aria-label={`查看运行 ${run.run_id}`} aria-pressed={run.run_id === selectedId} onClick={() => select(run.run_id)}>
                      <span className="run-item-top"><strong>{scenarioLabels[run.scenario]}</strong><span className={`run-status ${run.status}`}>{runStatusLabels[run.status]}</span></span>
                      <span className="run-item-id">{run.scenario} / {run.run_id}</span>
                      <time dateTime={new Date(run.created_at * 1000).toISOString()}>{date(run.created_at)}</time>
                    </button></li>)}
                  </ul>
                ) : !listError ? <div className="run-placeholder"><Clock3 size={26} aria-hidden="true" /><h3>还没有运行记录</h3><p>从项目 CLI 使用 sandbox-check 开始记录。已有历史执行不会自动补录；这里不展示项目开发测试作为你的任务。</p></div> : <p className="run-placeholder">列表暂不可用，请重试读取。</p>}
              </div>
              <section className="run-detail" aria-label="运行详情" aria-busy={detailLoading}>
                {!selectedId ? <div className="run-placeholder"><h3>选择一次运行</h3><p>查看状态变化与可校验的报告。刷新列表会保留你的选择。</p></div> : detailLoading ? <p className="run-placeholder" role="status">正在读取运行详情…</p> : detailError ? <div className="run-error" role="alert"><p>{detailError}</p><button className="text-link" onClick={reload}>重试读取详情</button></div> : current && <>
                  <div className="run-detail-heading"><h2>运行详情</h2><span className={`run-status ${current.run.status}`}>{runStatusLabels[current.run.status]}</span></div>
                  {current.run.status === "outcome_unknown" && <p className="run-unknown">未能确认执行结果；这不代表执行没有发生，也不触发自动重试。</p>}
                  <dl className="run-facts">
                    <div><dt>运行 ID</dt><dd><code>{current.run.run_id}</code></dd></div>
                    <div><dt>执行 ID</dt><dd><code>{current.run.attempt_id ?? "尚未领取"}</code></dd></div>
                    <div><dt>配置 / 场景</dt><dd>{scenarioLabels[current.run.scenario]}（{current.run.scenario}） / {current.run.profile}</dd></div>
                    <div><dt>状态版本</dt><dd>{current.run.version}</dd></div>
                    <div><dt>创建时间</dt><dd>{date(current.run.created_at)}</dd></div>
                    <div><dt>更新时间</dt><dd>{date(current.run.updated_at)}</dd></div>
                    <div><dt>执行资源状态</dt><dd>{current.run.executor_state ? executorLabels[current.run.executor_state] : "尚无对账记录"}</dd></div>
                    <div><dt>租约截止</dt><dd>{current.run.lease_until === null ? "无有效租约" : date(current.run.lease_until)}</dd></div>
                  </dl>
                  <details className="run-digests"><summary>查看输入与报告摘要</summary><dl className="run-facts">
                    <div><dt>配置 SHA-256</dt><dd><code>{current.run.config_sha256}</code></dd></div>
                    <div><dt>用例 SHA-256</dt><dd><code>{current.run.case_sha256}</code></dd></div>
                    <div><dt>报告 SHA-256</dt><dd><code>{current.run.report_sha256 ?? "暂无报告"}</code></dd></div>
                  </dl></details>
                  <div className="run-report"><button className="download" onClick={() => void download(current.run)} disabled={!current.run.report_sha256 || downloadLoading}><ArrowDownToLine size={14} aria-hidden="true" />{downloadLoading ? "校验报告中…" : "下载运行报告"}</button><p>{current.run.report_sha256 ? "下载前校验结构、执行关联与 SHA-256，保留服务端原始报告字节。" : "此运行尚无可下载的报告。"}</p><p role="status">{downloadNotice}</p></div>
                  <h3 className="run-events-heading">状态事件</h3>
                  {current.events.length ? <ol className="run-events">{current.events.map(event => <li key={event.event_id}><span className="run-event-version">v{event.version}</span><div><strong>{eventLabels[event.kind]}</strong><time dateTime={new Date(event.created_at * 1000).toISOString()}>{date(event.created_at)}</time><code>{event.event_id}</code></div></li>)}</ol> : <p className="run-note">没有可显示的状态事件。</p>}
                </>}
              </section>
            </div>
          </section>
          <WorkspaceFooter />
        </div>
      </main>
    </div>
  );
}
