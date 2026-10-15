"use client";

import { useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Info, Square, XCircle } from "lucide-react";
import { activeStatus, eventLabels, executorLabels, RunDetail as Detail, runDurationMs, runStatusLabels, RunView, scenarioLabels } from "../lib/runs";
import { reproductionResult, statusSentence } from "../lib/reproduction-result";
import { durationBetween, formatDateTime, formatDuration, formatTime } from "../lib/format";
import { runTone } from "../lib/tones";
import RunReport, { DownloadReportButton, FullId, ReportFacts, useVerifiedReport } from "./run-report";
import { CopyId } from "./ui/copy-id";
import { Skeleton } from "./ui/skeleton";
import { StatusBadge, StatusDot } from "./ui/status";

export type StopState = "sending" | "requested";

function ResultIcon({ tone }: { tone: "pass" | "fail" | "unknown" | "neutral" }) {
  const Icon = { pass: CheckCircle2, fail: XCircle, unknown: AlertTriangle, neutral: Info }[tone];
  return <Icon size={16} aria-hidden="true" />;
}

export default function RunDetail({ detail, cancellable, stopState, onStop, refreshKey, announce = true }: {
  detail: Detail; cancellable: boolean; stopState?: StopState; onStop: (run: RunView) => void; refreshKey: number; announce?: boolean;
}) {
  const run = detail.run;
  const report = useVerifiedReport(run, refreshKey);
  const [initialEvents] = useState(() => new Set(detail.events.map(event => event.event_id)));
  const active = activeStatus(run.status);
  const duration = runDurationMs(run);
  const result = report.report ? reproductionResult(run, report.report) : null;
  // Until the report has been verified or rejected, show a placeholder rather than the "no verifiable report" sentence.
  const pendingReport = !result && !!run.report_sha256 && !report.failure;
  const summary = result ?? statusSentence(run);
  const first = detail.events[0]?.created_at ?? run.created_at;
  return <article className="run-view" aria-labelledby="run-detail-title">
    {/* A button, not a #hash link: a hash entry has no router state, so Back would desync the URL from the selected run. */}
    <button type="button" className="run-back link small" onClick={() => {
      document.getElementById("run-list")?.scrollIntoView({ block: "start" });
      document.getElementById("run-list-heading")?.focus({ preventScroll: true });
    }}><ArrowLeft size={13} aria-hidden="true" />返回列表</button>
    <header className="run-detail-head">
      <div className="run-detail-title">
        <h2 id="run-detail-title">{scenarioLabels[run.scenario]}</h2>
        <span role="status" className="run-status-badge"><StatusBadge tone={runTone(run.status)}>{runStatusLabels[run.status]}</StatusBadge></span>
        <CopyId value={run.run_id} label="运行 ID" />
      </div>
      <div className="run-detail-actions">
        {cancellable && active && <button type="button" className="btn btn-sm btn-danger" disabled={!!stopState} aria-busy={!!stopState || undefined} onClick={() => onStop(run)}>
          <Square size={12} aria-hidden="true" />{stopState ? "正在停止…" : "停止"}
        </button>}
        <DownloadReportButton run={run} state={report} />
      </div>
      <p className="run-detail-meta">
        <span>开始于 <time dateTime={new Date(run.created_at * 1000).toISOString()} className="tabular">{formatDateTime(run.created_at)}</time></span>
        {duration !== null && <><span aria-hidden="true">·</span><span>耗时 <span className="tabular">{formatDuration(duration)}</span></span></>}
      </p>
    </header>

    {pendingReport ? <div className="run-result-skeleton" role="status" aria-busy="true"><span className="sr-only">正在读取结果…</span><Skeleton height={56} /></div>
      : <div className="run-result" data-tone={summary.tone}>
        <ResultIcon tone={summary.tone} />
        <div><h3>{summary.title}</h3><p>{summary.detail}</p></div>
      </div>}

    <section className="run-section" aria-labelledby="events-heading">
      <div className="run-section-head"><h3 id="events-heading">状态变化</h3></div>
      {detail.events.length || active ? <ol className="timeline">
        {detail.events.map((event, index) => {
          const last = index === detail.events.length - 1 && !active;
          const offset = durationBetween(first, event.created_at);
          return <li key={event.event_id} className={initialEvents.has(event.event_id) ? undefined : "flash"}>
            <StatusDot tone={last && event.kind !== "created" ? runTone(run.status) : "neutral"} />
            <span className="timeline-label">{eventLabels[event.kind]}</span>
            <time className="timeline-time" dateTime={new Date(event.created_at * 1000).toISOString()} title={formatDateTime(event.created_at)}>{formatTime(event.created_at)}</time>
            <span className="timeline-offset tabular">{index === 0 ? "" : `+${formatDuration(offset)}`}</span>
          </li>;
        })}
        {active && <li className="timeline-live">
          <StatusDot tone="running" />
          <span className="timeline-label">{run.status === "queued" ? "等待开始…" : stopState === "requested" ? "正在停止…" : "运行中…"}</span>
          <span className="timeline-time subtle">现在</span>
          <span />
        </li>}
      </ol> : <p className="run-empty-line">没有状态记录。</p>}
    </section>

    <RunReport run={run} state={report} announce={announce} />

    <details className="run-tech">
      <summary>技术详情</summary>
      <dl className="meta-list">
        <div><dt>运行 ID</dt><dd><FullId value={run.run_id} label="运行 ID" /></dd></div>
        <div><dt>尝试 ID</dt><dd>{run.attempt_id ? <FullId value={run.attempt_id} label="尝试 ID" /> : "尚未开始"}</dd></div>
        <div><dt>场景</dt><dd><code translate="no">{run.profile} / {run.scenario}</code></dd></div>
        <div><dt>状态版本</dt><dd className="tabular">{run.version}</dd></div>
        <div><dt>更新时间</dt><dd className="tabular">{formatDateTime(run.updated_at)}</dd></div>
        <div><dt>容器状态</dt><dd>{run.executor_state ? executorLabels[run.executor_state] : "未核对"}</dd></div>
        <div><dt>配置 SHA-256</dt><dd><FullId value={run.config_sha256} label="配置摘要" /></dd></div>
        <div><dt>用例 SHA-256</dt><dd><FullId value={run.case_sha256} label="用例摘要" /></dd></div>
        <div><dt>报告 SHA-256</dt><dd>{run.report_sha256 ? <FullId value={run.report_sha256} label="报告摘要" /> : "暂无报告"}</dd></div>
        {report.report && <ReportFacts report={report.report} />}
      </dl>
    </details>
  </article>;
}

/** Placeholder with the detail's shape while the first read is in flight. */
export function RunDetailSkeleton() {
  return <div className="run-detail-skeleton" role="status" aria-busy="true">
    <span className="sr-only">正在读取运行详情…</span>
    <div style={{ display: "flex", gap: 10, alignItems: "center" }}><Skeleton width={96} height={20} /><Skeleton width={72} height={20} /></div>
    <Skeleton width="45%" height={11} />
    <Skeleton height={56} />
    <Skeleton width="30%" height={13} />
    <Skeleton width="60%" />
    <Skeleton width="55%" />
    <Skeleton width="62%" />
  </div>;
}
