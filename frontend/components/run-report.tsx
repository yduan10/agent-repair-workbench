"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, RefreshCw } from "lucide-react";
import { loadVerifiedReport, runError, RunView, SandboxReport } from "../lib/runs";
import { saveDownload } from "../lib/reproductions";

const checks = { passed: "通过", failed: "不通过", not_checked: "未检查", skipped: "已跳过" };
const outcomes = { completed: "调用完成", precheck_rejected: "预检拒绝", unsupported: "暂不支持", tool_error: "工具返回错误", transport_error: "传输错误", protocol_error: "协议错误", outcome_unknown: "结果未知" };
const cleanup = { not_created: "未创建容器", removed: "已回收", unconfirmed: "回收未确认" };
export default function RunReport({ run, refreshKey }: { run: RunView; refreshKey: number }) {
  const [report, setReport] = useState<SandboxReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState("");
  const request = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const currentRun = useRef(run); currentRun.current = run;
  const identity = `${run.run_id}:${run.attempt_id}:${run.report_sha256}`;

  async function read(download: boolean) {
    // A click may replace an automatic summary read; never leave a late download alive.
    if (download && busy.current) return;
    busy.current = download;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const target = currentRun.current;
    setLoading(true); setFailure(""); setNotice("");
    try {
      const value = await loadVerifiedReport(target, controller.signal);
      if (controller.signal.aborted) return;
      setReport(value.report);
      if (download) { saveDownload(value.bytes, `run-${target.run_id}.json`); setNotice("报告校验通过，已开始下载。"); }
    } catch (error) {
      if (!controller.signal.aborted) { setReport(null); setFailure(runError(error)); }
    } finally {
      if (!controller.signal.aborted) { busy.current = false; setLoading(false); }
    }
  }
  useEffect(() => {
    setReport(null); setFailure(""); setNotice(""); busy.current = false;
    if (currentRun.current.report_sha256) void read(false);
    return () => request.current?.abort();
  }, [identity, refreshKey]);
  const findings = report ? [...report.mcp.preflight_findings, ...(report.mcp.contract_report?.findings ?? [])] : [];
  return <section className="run-report" aria-labelledby="report-heading">
    <div className="run-report-heading"><h3 id="report-heading">执行报告</h3>{report && <span className="verified-label">结构、关联与摘要已校验</span>}</div>
    {loading && !report && <p role="status">正在校验报告…</p>}
    {failure && <div className="run-error" role="alert"><p>{failure}</p><button className="text-link" onClick={() => void read(false)} disabled={loading}><RefreshCw size={13} aria-hidden="true" />重新读取报告</button></div>}
    {report && <>
      <dl className="report-summary"><div><dt>调用结果</dt><dd>{outcomes[report.mcp.adapter_outcome]}</dd></div><div><dt>MCP 报告耗时</dt><dd>{report.mcp.elapsed_ms.toLocaleString("zh-CN")} ms</dd></div><div><dt>资源回收</dt><dd className={report.execution.cleanup === "unconfirmed" ? "report-warning" : ""}>{cleanup[report.execution.cleanup]}</dd></div></dl>
      <p className="report-checks">输入检查：{report.mcp.contract_report ? checks[report.mcp.contract_report.checks.input] : "未检查"}；输出检查：{report.mcp.contract_report ? checks[report.mcp.contract_report.checks.output] : "未检查"}。</p>
      {report.execution.error && <p className="run-unknown">执行器报告错误代码：<code>{report.execution.error}</code></p>}
      {findings.length ? <ul className="report-findings" aria-label="已验证报告发现">{findings.map((finding, index) => <li key={index}><code>{finding.code}</code><span>{finding.phase} · 数据路径 <code>{finding.instance_path || "/"}</code></span><span>规则路径 <code>{finding.schema_path || "/"}</code></span></li>)}</ul> : <p className="run-note">报告未列出具体问题代码；请结合调用结果与实际完成的检查判断，不能据此认定所有检查通过。</p>}
      {report.mcp.contract_report?.findings_truncated && <p className="run-note">报告问题列表已截断，未展示全部发现。</p>}
    </>}
    <button className="download" onClick={() => void read(true)} disabled={!run.report_sha256 || (loading && busy.current)}><ArrowDownToLine size={14} aria-hidden="true" />{loading && busy.current ? "校验报告中…" : "下载运行报告"}</button>
    <p>{run.report_sha256 ? "下载前重新核验报告，保留服务端原始字节。" : "此运行尚无可下载的报告。"}</p><p role="status">{notice}</p>
  </section>;
}
