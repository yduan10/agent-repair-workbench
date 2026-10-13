"use client";

import { useEffect, useRef, useState } from "react";
import { Square } from "lucide-react";
import { cancelReproduction } from "../lib/reproductions";
import { eventLabels, executorLabels, RunDetail as Detail, runStatusLabels, scenarioLabels } from "../lib/runs";
import RunReport from "./run-report";
export function runDate(seconds: number) { return new Date(seconds * 1000).toLocaleString("zh-CN", { hour12: false }); }
export function activeStatus(status: string) { return status === "running" || status === "queued"; }

export default function RunDetail({ detail, cancellable, onChanged, refreshKey }: { detail: Detail; cancellable: boolean; onChanged: () => void; refreshKey: number }) {
  const [cancelState, setCancelState] = useState<"idle" | "sending" | "requested">("idle");
  const [notice, setNotice] = useState("");
  const guard = useRef(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function cancel() {
    if (guard.current || !cancellable || !activeStatus(detail.run.status)) return;
    guard.current = true; setCancelState("sending"); setNotice("");
    const controller = new AbortController(); request.current = controller;
    try {
      const result = await cancelReproduction(detail.run.run_id, controller.signal);
      if (controller.signal.aborted) return;
      setCancelState(result.status === "cancel_requested" ? "requested" : "idle");
      setNotice(result.status === "cancel_requested" ? "已请求停止，正在等待执行器回收与最终记录。已发出的调用可能仍有结果。" : "运行已经结束，正在查询最终记录。");
      onChanged();
    } catch {
      if (!controller.signal.aborted) { setCancelState("idle"); setNotice("停止请求结果未确认。请查询真实状态，不要将此提示视为已停止。"); onChanged(); }
    } finally { guard.current = false; }
  }
  const run = detail.run;
  return <>
    <div className="run-detail-heading"><div><h2>{scenarioLabels[run.scenario]}</h2><p>{runDate(run.created_at)}</p></div><span role="status" className={`run-status ${run.status}`}>{runStatusLabels[run.status]}</span></div>
    {run.status === "outcome_unknown" && <p className="run-unknown">未能确认执行结果；这不代表执行没有发生，也不触发自动重试。请先通过 CLI 对账核对资源。</p>}
    {cancellable && activeStatus(run.status) && <button className="download run-cancel" disabled={cancelState !== "idle"} onClick={() => void cancel()}><Square size={13} aria-hidden="true" />{cancelState === "sending" ? "正在请求停止…" : cancelState === "requested" ? "已请求停止" : "请求停止运行"}</button>}
    <p className="run-note" role="status">{activeStatus(run.status) ? notice : ""}</p>
    {activeStatus(run.status) && <p className="run-note">正在定期读取真实状态。离开页面会停止读取，服务端任务继续运行。</p>}
    <RunReport run={run} refreshKey={refreshKey} />
    <section className="execution-events" aria-labelledby="events-heading"><h3 id="events-heading">执行事件</h3><p className="run-note">来自持久记录的结构化状态事件，不是 shell 输出。</p>
      {detail.events.length ? <ol className="run-events">{detail.events.map(event => <li key={event.event_id}><span className="run-event-version">v{event.version}</span><div><strong>{eventLabels[event.kind]}</strong><time dateTime={new Date(event.created_at * 1000).toISOString()}>{runDate(event.created_at)}</time></div></li>)}</ol> : <p className="run-note">没有可显示的状态事件。</p>}
    </section>
    <details className="run-digests"><summary>技术详情：ID、版本与摘要</summary><dl className="run-facts">
      <div><dt>运行 ID</dt><dd><code>{run.run_id}</code></dd></div><div><dt>执行 ID</dt><dd><code>{run.attempt_id ?? "尚未领取"}</code></dd></div>
      <div><dt>配置 / 场景</dt><dd>{run.profile} / {run.scenario}</dd></div><div><dt>状态版本</dt><dd>{run.version}</dd></div><div><dt>更新时间</dt><dd>{runDate(run.updated_at)}</dd></div>
      <div><dt>执行资源状态</dt><dd>{run.executor_state ? executorLabels[run.executor_state] : "尚无对账记录"}</dd></div><div><dt>租约截止</dt><dd>{run.lease_until === null ? "无有效租约" : runDate(run.lease_until)}</dd></div>
      <div><dt>配置 SHA-256</dt><dd><code>{run.config_sha256}</code></dd></div><div><dt>用例 SHA-256</dt><dd><code>{run.case_sha256}</code></dd></div><div><dt>报告 SHA-256</dt><dd><code>{run.report_sha256 ?? "暂无报告"}</code></dd></div>
      {detail.events.map(event => <div key={event.event_id}><dt>事件 v{event.version} ID</dt><dd><code>{event.event_id}</code></dd></div>)}
    </dl></details>
  </>;
}
