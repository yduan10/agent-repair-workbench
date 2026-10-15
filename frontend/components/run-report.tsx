"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, RefreshCw, ShieldCheck } from "lucide-react";
import { loadVerifiedReport, runError, RunView, SandboxReport } from "../lib/runs";
import { saveDownload } from "../lib/reproductions";
import { findingLabels } from "../lib/report";
import { formatBytes, formatDuration, formatNumber } from "../lib/format";
import { Callout } from "./ui/callout";
import { CopyButton } from "./ui/copy-id";
import { PathTrail } from "./ui/path-trail";
import { Skeleton } from "./ui/skeleton";
import { useToast } from "./ui/toast";

export const checkLabels = { passed: "通过", failed: "不通过", not_checked: "未检查", skipped: "已跳过" } as const;
export const outcomeLabels = { completed: "调用完成", precheck_rejected: "调用前被拒绝", unsupported: "暂不支持", tool_error: "工具返回错误", transport_error: "传输错误", protocol_error: "协议错误", outcome_unknown: "结果未知" } as const;
export const cleanupLabels = { not_created: "未创建容器", removed: "已清理", unconfirmed: "未确认清理" } as const;
const checkTone = { passed: "pass", failed: "fail", not_checked: "neutral", skipped: "neutral" } as const;
const phaseLabels: Record<string, string> = { input: "参数", arguments: "参数", result: "返回结果", output: "返回结果", adapter: "调用", preflight: "调用前检查" };
const extraFindings: Record<string, string> = { call_timeout: "调用超时", response_lost: "响应丢失", transport_error: "传输错误", protocol_error: "协议错误" };

export type VerifiedReport = {
  report: SandboxReport | null;
  loading: boolean;
  downloading: boolean;
  failure: string;
  retry: () => void;
  download: () => void;
};

/** Reads and verifies (schema, record/attempt association, SHA-256) the run report.
 * Downloads always re-read and re-verify the server bytes. Aborts on run change/unmount. */
export function useVerifiedReport(run: RunView, refreshKey: number): VerifiedReport {
  const toast = useToast();
  const [report, setReport] = useState<SandboxReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [failure, setFailure] = useState("");
  const request = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const currentRun = useRef(run);
  useEffect(() => { currentRun.current = run; });
  const identity = `${run.run_id}:${run.attempt_id}:${run.report_sha256}`;

  const read = useCallback(async (download: boolean) => {
    // A click may replace an automatic summary read; never leave a late download alive.
    if (download && busy.current) return;
    busy.current = download;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const target = currentRun.current;
    setLoading(true); setDownloading(download); setFailure("");
    try {
      const value = await loadVerifiedReport(target, controller.signal);
      if (controller.signal.aborted) return;
      setReport(value.report);
      if (download) { saveDownload(value.bytes, `run-${target.run_id}.json`); toast.show({ tone: "pass", message: "已开始下载报告。" }); }
    } catch (error) {
      if (!controller.signal.aborted) { setReport(null); setFailure(runError(error)); }
    } finally {
      if (!controller.signal.aborted) { busy.current = false; setLoading(false); setDownloading(false); }
    }
  }, [toast]);

  useEffect(() => {
    setReport(null); setFailure(""); setDownloading(false); busy.current = false;
    if (currentRun.current.report_sha256) void read(false);
    return () => request.current?.abort();
  }, [identity, refreshKey, read]);

  return { report, loading, downloading, failure, retry: () => void read(false), download: () => void read(true) };
}

export function DownloadReportButton({ run, state }: { run: RunView; state: VerifiedReport }) {
  return <button type="button" className="btn btn-sm" onClick={state.download} disabled={!run.report_sha256 || state.downloading} aria-busy={state.downloading || undefined}
    title={run.report_sha256 ? "下载前重新核验报告摘要" : "这条运行没有生成报告"}>
    <ArrowDownToLine size={13} aria-hidden="true" />{state.downloading ? "正在下载…" : "下载报告"}
  </button>;
}

function findingTitle(code: string) {
  return findingLabels[code]?.[0] ?? extraFindings[code] ?? null;
}

/** Report body: verdict summary, contract findings with JSON Pointer paths. */
export default function RunReport({ run, state, announce = true }: { run: RunView; state: VerifiedReport; announce?: boolean }) {
  const { report, loading, failure } = state;
  const findings = report ? [...report.mcp.preflight_findings, ...(report.mcp.contract_report?.findings ?? [])] : [];
  const contract = report?.mcp.contract_report ?? null;
  const unchecked = contract ? [contract.checks.input, contract.checks.output].some(value => value === "not_checked" || value === "skipped") : true;
  return <section className="run-section report-section" aria-labelledby="report-heading">
    <div className="run-section-head">
      <h3 id="report-heading">运行报告</h3>
      {report && <span className="report-verified" title="结构、运行与尝试 ID 关联、SHA-256 摘要均已核验"><ShieldCheck size={13} aria-hidden="true" />已校验</span>}
    </div>
    {!run.report_sha256 ? <p className="run-empty-line">{run.status === "running" || run.status === "queued" ? "运行结束后生成报告。" : "这条运行没有生成报告。"}</p>
      : loading && !report ? <div className="report-skeleton" role="status" aria-busy="true"><span className="sr-only">正在读取报告…</span><Skeleton height={44} /><Skeleton width="70%" /><Skeleton width="45%" /></div>
      : failure ? <Callout tone="fail" title="无法显示报告" role={announce ? "alert" : undefined}
        actions={<button type="button" className="btn btn-sm" onClick={state.retry} disabled={loading}><RefreshCw size={13} aria-hidden="true" />重试</button>}>{failure}</Callout>
      : report && <>
        <dl className="report-facts">
          <div><dt>调用结果</dt><dd>{outcomeLabels[report.mcp.adapter_outcome]}</dd></div>
          <div><dt>参数检查</dt><dd data-tone={contract ? checkTone[contract.checks.input] : "neutral"}>{contract ? checkLabels[contract.checks.input] : "未检查"}</dd></div>
          <div><dt>返回结果检查</dt><dd data-tone={contract ? checkTone[contract.checks.output] : "neutral"}>{contract ? checkLabels[contract.checks.output] : "未检查"}</dd></div>
          <div><dt>调用耗时</dt><dd className="tabular">{formatDuration(report.mcp.elapsed_ms)}</dd></div>
          <div><dt>容器清理</dt><dd data-tone={report.execution.cleanup === "unconfirmed" ? "unknown" : "neutral"}>{cleanupLabels[report.execution.cleanup]}</dd></div>
        </dl>
        {report.execution.error && <Callout tone="fail" title="运行环境错误"><code translate="no">{report.execution.error}</code>{report.execution.oom_killed ? "，容器因内存超限被终止。" : ""}</Callout>}
        {!report.execution.error && report.execution.oom_killed && <Callout tone="fail" title="运行环境错误">容器因内存超限被终止。</Callout>}
        <div className="report-issues">
          <h4>不符合项 <span className="subtle tabular">{findings.length}</span></h4>
          {findings.length ? <ul className="finding-list" aria-label="不符合项">{findings.map((finding, index) => {
            const title = findingTitle(finding.code);
            return <li key={index}>
              <div className="finding-top">
                <strong>{title ?? <code translate="no">{finding.code}</code>}</strong>
                {title && <code className="finding-code" translate="no">{finding.code}</code>}
                <span className="finding-phase">{phaseLabels[finding.phase] ?? finding.phase}</span>
              </div>
              <dl className="finding-paths">
                <div><dt>字段路径</dt><dd><PathTrail pointer={finding.instance_path} label="字段路径" /></dd></div>
                {finding.schema_path && <div><dt>契约路径</dt><dd><PathTrail pointer={finding.schema_path} tone="neutral" label="契约路径" /></dd></div>}
              </dl>
            </li>;
          })}</ul> : <p className="run-empty-line">没有不符合项。{unchecked ? "显示「未检查」或「已跳过」的项目没有执行检查。" : ""}</p>}
          {contract?.findings_truncated && <p className="run-empty-line">只显示前 50 项。</p>}
        </div>
        <p className="report-next small subtle">想让模型分析这类问题，可以对内置案例 <Link className="link" href="/workspace/diagnosis">发起分析</Link>。</p>
      </>}
  </section>;
}

/** Full technical identifier with a one-click copy button. */
export function FullId({ value, label }: { value: string; label: string }) {
  return <span className="full-id"><code translate="no">{value}</code><CopyButton value={value} label={label} className="btn btn-ghost btn-icon btn-sm" /></span>;
}

/** Technical identifiers and execution facts from the verified report (for 技术详情). */
export function ReportFacts({ report }: { report: SandboxReport }) {
  const execution = report.execution;
  const source = report.mcp.source;
  return <>
    <div><dt>镜像</dt><dd>{execution.image_id ? <FullId value={execution.image_id} label="镜像 ID" /> : "—"}</dd></div>
    <div><dt>隔离策略</dt><dd><code translate="no">{execution.policy}</code></dd></div>
    <div><dt>随机种子</dt><dd className="tabular">{execution.seed ?? "—"}</dd></div>
    <div><dt>标准输出</dt><dd className="tabular">{formatBytes(execution.stdout_bytes)}</dd></div>
    <div><dt>错误输出</dt><dd className="tabular">{formatBytes(execution.stderr_bytes)}</dd></div>
    <div><dt>消息帧</dt><dd className="tabular">{formatNumber(execution.frames)}</dd></div>
    <div><dt>退出码</dt><dd className="tabular">{execution.container_exit_code ?? "—"}</dd></div>
    <div><dt>内存超限</dt><dd>{execution.oom_killed ? "是" : "否"}</dd></div>
    <div><dt>容器清理</dt><dd>{cleanupLabels[execution.cleanup]}</dd></div>
    <div><dt>调用 ID</dt><dd><FullId value={report.mcp.invocation_id} label="调用 ID" /></dd></div>
    <div><dt>协议 / SDK</dt><dd><code translate="no">{source.protocol_version ?? "—"} · mcp {source.sdk_version}</code></dd></div>
    {report.mcp.contract_report && <div><dt>检查器</dt><dd><code translate="no">{report.mcp.contract_report.checker_version}</code></dd></div>}
    {source.tool_schema_sha256 && <div><dt>工具契约 SHA-256</dt><dd><FullId value={source.tool_schema_sha256} label="工具契约摘要" /></dd></div>}
  </>;
}
