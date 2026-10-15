"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Download } from "lucide-react";
import { EvidenceProvider, EvidenceReferences as Evidence, EvidenceLibrary } from "./analysis-evidence";
import { CommandLine } from "./analysis-console";
import { StatusBadge } from "./ui/status";
import { RelativeTime } from "./ui/relative-time";
import { CopyButton } from "./ui/copy-id";
import { AnalysisDetail, analysisStatus, assessmentLabels, describeEvent, errorLabels, intentLabels, reasonLabels, roleLabels, sourceLabels } from "../lib/analyses";
import { reconcileCommand } from "../lib/analysis-runs";
import { analysisTone } from "../lib/tones";
import { durationBetween, formatDateTime, formatDuration, formatNumber, formatTime, shortId, toDate } from "../lib/format";

/** Kept for pages that still show a copyable CLI command with a visible label. */
export function AnalysisCommand({ value, label }: { value: string; label: string }) {
  return <CommandLine value={value} label={label} />;
}

const PAGE = 12;
const KEY_EVENTS = new Set(["role_concluded", "tool_completed", "model_unknown", "finished", "reconciled"]);

function EventLog({ events }: { events: AnalysisDetail["events"] }) {
  const [scope, setScope] = useState("key");
  const [role, setRole] = useState("all");
  const [page, setPage] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  const filtered = events.filter(({ event: e }) => (role === "all" || e.role === role) && (scope === "all" || e.error_code || KEY_EVENTS.has(e.kind)));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const current = Math.min(page, pages - 1);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 0; }, [current, scope, role]);
  return <section className="an-block an-events" aria-labelledby="analysis-events-title">
    <div className="an-block-head">
      <h3 id="analysis-events-title">执行过程<span className="count tabular">{events.length}</span></h3>
      <div className="an-log-filters">
        <label><span className="sr-only">事件</span><select className="select an-select-sm" aria-label="事件" value={scope} onChange={event => { setScope(event.target.value); setPage(0); }}><option value="key">关键事件</option><option value="all">全部事件</option></select></label>
        <label><span className="sr-only">角色</span><select className="select an-select-sm" aria-label="角色" value={role} onChange={event => { setRole(event.target.value); setPage(0); }}><option value="all">全部角色</option>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
    </div>
    <div ref={scroll} className="an-log" tabIndex={0} role="region" aria-label="执行过程列表">
      {filtered.length ? <ol>{filtered.slice(current * PAGE, (current + 1) * PAGE).map(item => {
        const { text, error } = describeEvent(item.event);
        return <li key={item.revision} data-level={error ? "error" : undefined}>
          <span className="an-log-index tabular" title={`第 ${item.revision + 1} 步`}>{item.revision + 1}</span>
          <time dateTime={toDate(item.created_at).toISOString()} title={formatDateTime(item.created_at)}>{formatTime(item.created_at)}</time>
          <span className="an-log-role">{item.event.role ? roleLabels[item.event.role] : "系统"}</span>
          <div className="an-log-text"><span>{text}</span><Evidence refs={item.event.evidence_refs} /></div>
        </li>;
      })}</ol> : <p className="an-log-empty">没有匹配的事件。<button type="button" className="link an-inline-button" onClick={() => { setScope("all"); setRole("all"); setPage(0); }}>显示全部事件</button></p>}
    </div>
    <div className="an-pagination">
      <span className="subtle small tabular" role="status">{filtered.length} 条{scope === "key" ? "关键事件" : "事件"}</span>
      <div><button type="button" className="btn btn-sm" disabled={current === 0} onClick={() => setPage(current - 1)}>上一页</button>
        <span className="tabular small" aria-live="polite">{current + 1} / {pages}</span>
        <button type="button" className="btn btn-sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>下一页</button></div>
    </div>
  </section>;
}

function Meter({ label, value, limit, reserved = 0, note, meter }: { label: string; value: number; limit: number; reserved?: number; note?: React.ReactNode; meter?: boolean }) {
  const pct = (n: number) => `${Math.min(100, (100 * n) / limit)}%`;
  return <div className="an-meter">
    <dt>{label}</dt>
    <dd>
      <span className="an-meter-value tabular"><strong>{formatNumber(value)}</strong><span className="subtle"> / {formatNumber(limit)}</span></span>
      <span className="an-meter-track" role={meter ? "meter" : undefined} aria-label={meter ? `${label}占预算` : undefined} aria-hidden={meter ? undefined : true}
        aria-valuemin={meter ? 0 : undefined} aria-valuemax={meter ? limit : undefined} aria-valuenow={meter ? value + reserved : undefined}
        aria-valuetext={meter ? `已确认 ${formatNumber(value)}${reserved ? `，待确认 ${formatNumber(reserved)}` : ""}，上限 ${formatNumber(limit)}` : undefined}>
        <span style={{ width: pct(value) }} />{reserved > 0 && <span className="reserved" style={{ width: pct(reserved) }} />}
      </span>
      {note && <span className="an-meter-note">{note}</span>}
    </dd>
  </div>;
}

function conclusion(detail: AnalysisDetail) {
  const s = detail.summary;
  if (s.state.phase !== "finished") return "分析正在进行，结果会自动更新。";
  switch (s.state.outcome) {
    case "proposal_only": return `已提出 ${s.proposal_count} 条修复建议，没有修改代码。`;
    case "outcome_unknown": return "分析中断或模型未返回用量，结果未确认。核对命令见下方「技术详情」。";
    case "check_complete": return "契约检查完成，不符合项见下方证据。";
    case "diagnosis_complete": return "诊断完成。诊断角色的结论是假设，可以通过复现确认。";
    case "budget_exceeded": return "用量达到预算上限，分析提前结束。已提交的结论保留在下方。";
    case "cancelled": return "分析已停止。已记录的事件和用量保留在下方。";
    case "inconclusive": return "证据不足，没有得出结论。";
    default: return "分析没有完成。原因见下方执行过程中标红的事件。";
  }
}

export default function AnalysisDetailView({ detail }: { detail: AnalysisDetail }) {
  const { summary: s, events } = detail;
  const known = s.usage.known_input_tokens + s.usage.known_output_tokens;
  const lastError = [...events].reverse().find(item => item.event.error_code)?.event.error_code;
  const roles = (["diagnosis", "repair", "verification"] as const).map(role => ({
    role,
    conclusion: [...events].reverse().find(v => v.event.kind === "role_concluded" && v.event.role === role)?.event,
    participated: events.some(v => v.event.role === role),
  }));
  const showRoles = s.state.intent !== "check_only" || roles.some(r => r.participated);
  const duration = durationBetween(s.started_at, s.finished_at);
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(detail, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `analysis-${s.task_id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <EvidenceProvider detail={detail}>
    <header className="an-detail-head">
      <div>
        <div className="an-detail-title"><h2>{analysisStatus(s)}</h2><StatusBadge tone={analysisTone(s)} variant="outline">{intentLabels[s.state.intent]}</StatusBadge></div>
        <p className="an-detail-meta tabular"><span>{sourceLabels[s.source_kind]}</span><span>开始于 <RelativeTime value={s.started_at} /></span><span>{duration === null ? "进行中" : `用时 ${formatDuration(duration)}`}</span></p>
      </div>
      <button type="button" className="btn btn-sm" onClick={download}><Download size={13} aria-hidden="true" />下载分析</button>
    </header>

    <p className="an-conclusion" data-tone={lastError || s.state.outcome === "outcome_unknown" ? "unknown" : undefined}>{conclusion(detail)}{lastError && <span className="an-conclusion-error">错误：{errorLabels[lastError]}（<code translate="no">{lastError}</code>）</span>}</p>

    {showRoles && <section className="an-block" aria-labelledby="analysis-roles-title">
      <h3 id="analysis-roles-title" className="an-block-title">角色结论</h3>
      <ol className="an-roles">{roles.map(({ role, conclusion: c, participated }) => <li key={role} data-state={c ? "concluded" : participated ? "participated" : "absent"}>
        <span className="an-role-name">{roleLabels[role]}</span>
        <div className="an-role-body">
          <strong>{c?.assessment ? assessmentLabels[c.assessment] : participated ? s.state.phase === "finished" ? "未提交结论" : "进行中" : "未参与"}</strong>
          {c?.reason_code && <span className="muted">{reasonLabels[c.reason_code]}</span>}
          {c && <Evidence refs={c.evidence_refs} />}
        </div>
      </li>)}</ol>
    </section>}

    <EvidenceLibrary />

    <section className="an-block" aria-labelledby="analysis-usage-title">
      <h3 id="analysis-usage-title" className="an-block-title">用量与预算</h3>
      <dl className="an-meters">
        <Meter label="Token" value={known} limit={s.budget.total_tokens} reserved={s.usage.reserved_tokens} meter
          note={!s.usage.usage_complete ? <span data-tone="unknown">用量待确认：预留 {formatNumber(s.usage.reserved_tokens)} 暂计入预算</span> : undefined} />
        <Meter label="模型调用" value={s.usage.model_calls} limit={s.budget.model_calls} />
        <Meter label="工具调用" value={s.usage.tool_calls} limit={s.budget.tool_calls} />
        <div className="an-meter"><dt>费用</dt><dd><span className="an-meter-value muted">未配置单价</span></dd></div>
      </dl>
    </section>

    <section className="an-block" aria-labelledby="analysis-linked-title">
      <h3 id="analysis-linked-title" className="an-block-title">关联复现</h3>
      {s.execution_record_ids.length ? <ul className="an-linked">{s.execution_record_ids.map(id => <li key={id}>
        <Link className="link" href={`/workspace/tasks?run=${id}`} title={id}>运行 <code translate="no">{shortId(id)}</code><ArrowUpRight size={13} aria-hidden="true" /></Link>
      </li>)}</ul> : <p className="muted small">本次分析没有运行复现。</p>}
    </section>

    <EventLog events={events} />

    <details className="an-tech">
      <summary>技术详情</summary>
      <div className="an-tech-body">
        <dl className="meta-list">
          <dt>分析 ID</dt><dd className="an-tech-value"><code translate="no">{s.task_id}</code><CopyButton value={s.task_id} label="分析 ID" className="btn btn-ghost btn-sm btn-icon" /></dd>
          <dt>摘要 SHA-256</dt><dd className="an-tech-value"><code translate="no">{detail.sha256}</code><CopyButton value={detail.sha256} label="摘要 SHA-256" className="btn btn-ghost btn-sm btn-icon" /></dd>
          <dt>摘要版本</dt><dd className="tabular">{s.summary_revision}</dd>
          <dt>模型配置摘要</dt><dd>{s.model_config_sha256 ? <code translate="no">{s.model_config_sha256}</code> : <span className="muted">未调用模型</span>}</dd>
          <dt>预算</dt><dd className="tabular">单次输出 {formatNumber(s.budget.output_tokens)} token · 修复建议 {s.proposal_count} / {s.budget.candidates} · 时限 {formatDuration(s.budget.timeout_seconds * 1000)}</dd>
        </dl>
        <p className="muted small">只保存结论和证据引用，不保存模型原文。分析中断后不会自动继续，可用下面的命令核对状态。</p>
        <CommandLine value={reconcileCommand(s.task_id)} label="核对命令" />
      </div>
    </details>
  </EvidenceProvider>;
}
