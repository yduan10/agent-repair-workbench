"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight, Copy, Download, Layers3, RefreshCw, ScanSearch } from "lucide-react";
import Sidebar from "./sidebar";
import WorkspaceFooter from "./workspace-footer";
import AgentContracts from "./agent-contracts";
import ModuleProgress from "./module-progress";
import { AnalysisDetail, SavedAnalysis, analysisStatus, assessmentLabels, eventLabels, intentLabels, loadAnalyses, loadAnalysis, reasonLabels, roleLabels, toolLabels } from "../lib/analyses";
import { runError } from "../lib/runs";
import { capabilities } from "../lib/capabilities";
const date = (value: string | number) => new Date(typeof value === "number" ? value * 1000 : value).toLocaleString("zh-CN", { hour12: false });
const number = (value: number) => value.toLocaleString("zh-CN");
function Command({ value, label }: { value: string; label: string }) {
  const [status, setStatus] = useState("");
  return <div className="analysis-command"><pre tabIndex={0} aria-label={label}><code>{value}</code></pre><button className="text-link" onClick={async () => { try { await navigator.clipboard.writeText(value); setStatus("已复制"); } catch { setStatus("复制失败，请选择命令后手动复制。"); } }}><Copy size={14} aria-hidden="true" />复制{label}</button><span role="status">{status}</span></div>;
}
function AnalysisView({ detail }: { detail: AnalysisDetail }) {
  const { summary: s, events } = detail;
  const used = s.usage.known_input_tokens + s.usage.known_output_tokens;
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(detail, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `analysis-${s.task_id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <>
    <header className="analysis-result-heading"><div><h2>{intentLabels[s.state.intent]}</h2><p>{s.source_kind === "synthetic" ? "审核过的合成案例" : "公开历史案例"} · {date(s.started_at)}</p></div><span className="analysis-status">{analysisStatus(s)}</span></header>
    <button className="download" onClick={download}><Download size={14} aria-hidden="true" />下载分析摘要</button>
    <p className="analysis-boundary">角色结论为诊断假设或建议；建议复核不代表补丁已应用或回归通过。</p>
    <ol className="analysis-roles" aria-label="角色参与状态">{(["diagnosis", "repair", "verification"] as const).map(role => {
      const conclusion = [...events].reverse().find(v => v.event.kind === "role_concluded" && v.event.role === role)?.event;
      const participated = events.some(v => v.event.role === role);
      return <li key={role} className={participated ? "participated" : ""}><strong>{roleLabels[role]}角色</strong><span>{conclusion?.assessment ? assessmentLabels[conclusion.assessment] : participated ? s.state.phase === "finished" ? "未提交结论" : "已参与" : "未参与"}</span>{conclusion?.reason_code && <small>{reasonLabels[conclusion.reason_code]}</small>}</li>;
    })}</ol>
    <section className="analysis-budget" aria-labelledby="analysis-budget-title"><h3 id="analysis-budget-title">调用与预算</h3><dl><div><dt>已知输入 token</dt><dd>{number(s.usage.known_input_tokens)}</dd></div><div><dt>已知输出 token</dt><dd>{number(s.usage.known_output_tokens)}</dd></div><div><dt>未结算预留 token</dt><dd>{number(s.usage.reserved_tokens)}</dd></div><div><dt>费用</dt><dd>未知</dd></div></dl>
      <div className="analysis-budget-track" role="meter" aria-label="已知用量与预留占总预算" aria-valuemin={0} aria-valuemax={s.budget.total_tokens} aria-valuenow={used + s.usage.reserved_tokens} aria-valuetext={`已知 ${used}，预留 ${s.usage.reserved_tokens}，上限 ${s.budget.total_tokens}`}><span style={{ width: `${100 * used / s.budget.total_tokens}%` }} /><span className="reserved" style={{ width: `${100 * s.usage.reserved_tokens / s.budget.total_tokens}%` }} /></div>
      <p>总 token 上限 {number(s.budget.total_tokens)}；输出预留上限 {number(s.budget.output_tokens)}。{s.usage.usage_complete ? "用量已结算；未配置计价，费用未知。" : "仍有未结算预留，不视作已消耗或可退还；费用未知。"}</p><p>模型调用 {s.usage.model_calls} / {s.budget.model_calls} · 工具调用 {s.usage.tool_calls} / {s.budget.tool_calls} · 建议 {s.proposal_count} / {s.budget.candidates}</p>
    </section>
    <section className="analysis-events" aria-labelledby="analysis-events-title"><h3 id="analysis-events-title">过程记录</h3><p>只展示结构化状态与证据引用，不保存模型原始文字。</p><ol>{events.map(item => <li key={item.revision}><span className="analysis-event-index" aria-label={`第 ${item.revision + 1} 步`}>{item.revision + 1}</span><div><div className="analysis-event-heading"><strong>{eventLabels[item.event.kind]}{item.event.role ? ` · ${roleLabels[item.event.role]}` : ""}</strong><time dateTime={new Date(item.created_at * 1000).toISOString()}>{date(item.created_at)}</time></div>
      {item.event.tool && <p>{toolLabels[item.event.tool]}</p>}{item.event.assessment && <p>{assessmentLabels[item.event.assessment]}{item.event.reason_code ? `：${reasonLabels[item.event.reason_code]}` : ""}</p>}
      {item.event.kind === "model_started" && <p>预留输入 {number(item.event.input_reserved!)} / 输出 {number(item.event.output_reserved!)} token</p>}{item.event.kind === "model_settled" && <p>已知输入 {number(item.event.known_input_tokens!)} / 输出 {number(item.event.known_output_tokens!)} token</p>}{item.event.kind === "model_unknown" && <p>用量未知，保留本次预留。</p>}{item.event.error_code && <p>状态代码 <code>{item.event.error_code}</code></p>}
      {item.event.evidence_refs.length > 0 && <details><summary>{item.event.evidence_refs.length} 项证据引用</summary><ul>{item.event.evidence_refs.map(ref => <li key={ref.evidence_id}><code>{ref.evidence_id}</code><small>SHA-256 <code>{ref.sha256}</code></small></li>)}</ul></details>}
    </div></li>)}</ol></section>
    <section className="analysis-linked" aria-labelledby="analysis-linked-title"><h3 id="analysis-linked-title">关联的实际运行</h3>{s.execution_record_ids.length ? <ul>{s.execution_record_ids.map(id => <li key={id}><Link href={`/workspace/tasks?run=${id}`}>查看运行 <code>{id}</code></Link></li>)}</ul> : <p>本次尚无隔离执行记录。读取或检查证据不等于执行复现。</p>}</section>
    <details className="analysis-technical"><summary>摘要、证据与恢复说明</summary><dl><div><dt>任务 ID</dt><dd><code>{s.task_id}</code></dd></div><div><dt>摘要 SHA-256（服务端校验）</dt><dd><code>{detail.sha256}</code></dd></div><div><dt>摘要版本</dt><dd>{s.summary_revision}</dd></div><div><dt>模型配置摘要</dt><dd><code>{s.model_config_sha256 ?? "未调用模型"}</code></dd></div></dl><p>进程中断后，只对账并保留预留，不自动续跑或重新调用。</p><Command value={`uv run --frozen agent-workbench analyses reconcile ${s.task_id}`} label="对账命令" /></details>
  </>;
}
export default function AnalysisHistory() {
  const [items, setItems] = useState<SavedAnalysis[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setListLoading(true); setListError("");
    loadAnalyses(controller.signal).then(value => { if (!controller.signal.aborted) { setItems(value); setLoaded(true); } }).catch(error => { if (!controller.signal.aborted) setListError(runError(error)); }).finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    setDetailLoading(true); setDetailError("");
    async function read() {
      try {
        const result = await loadAnalysis(selected!, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(result); setDetailError(""); setItems(old => old.map(item => item.summary.task_id === selected ? { summary: result.summary, sha256: result.sha256 } : item));
        if (result.summary.state.phase !== "finished") timer = setTimeout(() => void read(), 2000);
      } catch (error) { if (!controller.signal.aborted) setDetailError(runError(error)); }
      finally { if (!controller.signal.aborted) setDetailLoading(false); }
    }
    void read(); return () => { controller.abort(); clearTimeout(timer); };
  }, [selected, refresh]);
  const current = detail?.summary.task_id === selected ? detail : null;
  const reload = () => setRefresh(value => value + 1);
  return <div className="shell"><a className="skip" href="#main">跳至分析记录</a><Sidebar /><main id="main"><header className="topbar"><div className="breadcrumb"><Layers3 size={16} aria-hidden="true" /><span>工作区</span><ChevronRight size={13} aria-hidden="true" /><strong>诊断分析</strong></div><span className="preview-status"><span />{capabilities.diagnosis.label}</span></header>
    <div className="main-content module-content analysis-content"><section className="intro"><div><h1>让每一步判断，都有据可查。</h1><p>从 CLI 发起受约束的分析，在这里核对角色结论、实际调用和预算。网页只读，候选建议尚不应用。</p></div></section>
      <section className="analysis-ledger" aria-label="分析记录"><div className="run-toolbar"><div><h2>分析与证据</h2><p>最近 50 次分析；来源与执行情况分别标注。</p></div><button className="download" disabled={listLoading || detailLoading} onClick={reload}><RefreshCw size={14} aria-hidden="true" />{listLoading ? "刷新中…" : "刷新分析"}</button></div>
        {listError && <div className="run-error" role="alert"><p>{listError}{loaded ? " 下方为上次读取的列表，可能已过时。" : ""}</p><button className="text-link" onClick={reload}>重试读取分析</button></div>}
        <div className="analysis-columns"><section className="analysis-main" aria-label="分析详情" aria-busy={detailLoading}>{detailError && <div className="run-error" role="alert"><p>{detailError}{current ? " 当前保留上次详情，自动更新已暂停。" : ""}</p><button className="text-link" onClick={reload}>重试读取详情</button></div>}
          {current ? <AnalysisView key={current.summary.task_id} detail={current} /> : selected ? detailLoading && <p role="status" className="run-placeholder">正在读取分析详情…</p> : <div className="analysis-empty"><ScanSearch size={30} aria-hidden="true" /><h2>{items.length ? "选择一次分析，核对它的推理过程。" : "第一份分析，从真实执行开始。"}</h2><p>这里只显示本机保存的真实分析记录。可先运行不调用模型的契约检查，或配置已有模型接口后发起诊断。</p><a className="text-link" href="#analysis-cli">查看启动方式</a></div>}
        </section><aside className="analysis-list" aria-label="最近分析"><h3>最近分析</h3>{listLoading && !loaded ? <p className="run-placeholder" role="status">正在读取分析记录…</p> : items.length ? <ul className="run-list">{items.map(item => <li key={item.summary.task_id}><button className={`run-item ${selected === item.summary.task_id ? "selected" : ""}`} aria-label={`查看分析 ${item.summary.task_id}`} aria-pressed={selected === item.summary.task_id} onClick={() => { if (selected !== item.summary.task_id) { setDetail(null); setDetailError(""); setSelected(item.summary.task_id); } }}><span className="run-item-top"><strong>{intentLabels[item.summary.state.intent]}</strong><span className="run-status">{analysisStatus(item.summary)}</span></span><time dateTime={item.summary.started_at}>{date(item.summary.started_at)}</time><span className="analysis-source">{item.summary.source_kind === "synthetic" ? "合成案例" : "公开历史案例"}</span></button></li>)}</ul> : <p className="run-placeholder">{listError ? "列表暂不可用，请重试。" : "尚无分析记录。执行 CLI 后刷新此页。"}</p>}</aside></div>
      </section>
      <section className="analysis-cli" id="analysis-cli" aria-labelledby="analysis-cli-title"><h2 id="analysis-cli-title">从本机开始一次分析</h2><p>在项目目录执行；模型凭据只从本机环境读取，不在网页填写。当前只开放两个审核过的合成案例。</p><details open={!items.length}><summary>CLI 启动与使用边界</summary><h3>初始化或升级本地记录库</h3><Command value="uv run --frozen agent-workbench runs init" label="初始化命令" /><p>已有记录时先按项目文档备份 SQLite 数据库。此操作不会调用模型。</p><h3>只检查契约，不调用模型</h3><Command value="uv run --frozen agent-workbench analyze --case output_mismatch --intent check_only" label="检查命令" /><h3>使用已配置的模型诊断</h3><Command value="uv run --frozen agent-workbench analyze --case output_mismatch --intent diagnose" label="诊断命令" /><p>模型可申请审核过的受控复现；需要预先准备本地隔离镜像。passing 是正常案例；propose_repair 意图只产出候选建议，不会应用补丁。用量未知时保留预留并终止，不自动重试。</p><Link className="text-link" href="/docs/24-p0-05b-runtime">查看模型接入与预算约束</Link></details></section>
      <AgentContracts /><details className="reproduction-progress"><summary>当前能力与后续计划</summary><ModuleProgress section="diagnosis" /></details><WorkspaceFooter />
    </div></main></div>;
}
