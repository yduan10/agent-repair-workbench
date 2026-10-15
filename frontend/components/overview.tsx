"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Braces, GitCompareArrows, Inbox, Layers3, RefreshCw, ScanSearch } from "lucide-react";
import { PageHeader } from "./ui/page-header";
import { StatusBadge, StatusDot, type Tone } from "./ui/status";
import { RelativeTime } from "./ui/relative-time";
import { SkeletonRows } from "./ui/skeleton";
import { EmptyState } from "./ui/empty-state";
import { Callout } from "./ui/callout";
import { useEnvironmentStatus } from "./ui/environment-context";
import { loadRuns, runStatusLabels, scenarioLabels } from "../lib/runs";
import { loadAnalyses, analysisStatus, intentLabels } from "../lib/analyses";
import { loadRepairs, caseLabels } from "../lib/repairs";
import { analysisTone, repairSummary, runTone } from "../lib/tones";
import { shortId, toDate } from "../lib/format";

type Source = "复现" | "分析" | "修复";
type Activity = { id: string; kind: "复现" | "分析" | "修复"; title: string; status: string; tone: Tone; at: number; href: string };

const starts = [
  { href: "/workbench", icon: Braces, title: "检查调用证据", text: "粘贴或导入一次工具调用，定位不符合契约的字段。" },
  { href: "/workspace/tasks", icon: Layers3, title: "运行复现", text: "在隔离容器里运行正常、错误、超时、响应丢失四种场景。" },
  { href: "/workspace/diagnosis", icon: ScanSearch, title: "发起分析", text: "让三个角色分析内置案例，给出带证据的结论。" },
];

export default function Overview() {
  const env = useEnvironmentStatus();
  const [items, setItems] = useState<Activity[] | null>(null);
  // Sources that failed to load. Any failure means the list is partial, so the empty state must not be shown.
  const [failed, setFailed] = useState<Source[]>([]);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      const [runs, analyses, repairs] = await Promise.allSettled([loadRuns(controller.signal), loadAnalyses(controller.signal), loadRepairs(controller.signal)]);
      if (controller.signal.aborted) return;
      const list: Activity[] = [];
      if (runs.status === "fulfilled") for (const run of runs.value) list.push({ id: run.run_id, kind: "复现", title: scenarioLabels[run.scenario], status: runStatusLabels[run.status], tone: runTone(run.status), at: toDate(run.created_at).getTime(), href: `/workspace/tasks?run=${run.run_id}` });
      if (analyses.status === "fulfilled") for (const { summary } of analyses.value) list.push({ id: summary.task_id, kind: "分析", title: intentLabels[summary.state.intent], status: analysisStatus(summary), tone: analysisTone(summary), at: toDate(summary.started_at).getTime(), href: `/workspace/diagnosis?analysis=${summary.task_id}` });
      if (repairs.status === "fulfilled") for (const task of repairs.value) list.push({ id: task.task_id, kind: "修复", title: caseLabels[task.case_id], status: repairSummary(task).label, tone: repairSummary(task).tone, at: toDate(task.started_at).getTime(), href: `/workspace/repairs?task=${task.task_id}` });
      setFailed(([["复现", runs], ["分析", analyses], ["修复", repairs]] as const).filter(([, result]) => result.status === "rejected").map(([kind]) => kind));
      setItems(list.sort((a, b) => b.at - a.at).slice(0, 10));
    })();
    return () => controller.abort();
  }, [reload]);
  const error = failed.length === 3;
  const retry = () => { setItems(null); setReload(value => value + 1); };
  const modelMissing = env.analysis && !env.analysis.model.configured;
  return <>
    <PageHeader title="总览" description="本机环境状态，以及最近的复现、分析和修复。" />

    <section aria-labelledby="env-heading">
      <div className="section-head"><h2 id="env-heading">本机环境</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={env.refresh}><RefreshCw size={13} aria-hidden="true" />重新检查</button></div>
      <div className="pane overview-env">
        {env.checks.map(check => <div key={check.key} className="overview-env-item">
          <div className="overview-env-top"><StatusDot tone={check.tone} /><span>{check.label}</span></div>
          <strong>{check.summary}</strong>
          {check.detail && <p>{check.detail}</p>}
          {check.href && <Link className="link small" href={check.href}>{check.tone === "running" ? "查看进行中的任务" : "查看处理方法"}</Link>}
        </div>)}
      </div>
    </section>

    <section className="section" aria-labelledby="start-heading">
      <div className="section-head"><h2 id="start-heading">开始</h2></div>
      <div className="overview-start">
        {starts.map(({ href, icon: Icon, title, text }) => <Link key={href} href={href} className="overview-start-item">
          <Icon size={18} aria-hidden="true" />
          <span><strong>{title}</strong><span>{href === "/workspace/diagnosis" && modelMissing ? "模型未配置时只能做契约检查。" : text}</span></span>
          <ArrowRight size={15} aria-hidden="true" />
        </Link>)}
      </div>
    </section>

    <section className="section" aria-labelledby="activity-heading">
      <div className="section-head"><h2 id="activity-heading">最近活动</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={retry}><RefreshCw size={13} aria-hidden="true" />刷新</button></div>
      <div className="pane">
        {items === null ? <SkeletonRows rows={5} label="正在读取最近活动…" />
          : error ? <div className="pane-body"><Callout tone="fail" title="无法读取记录" role="alert" actions={<button type="button" className="btn btn-sm" onClick={retry}>重试</button>}>本机服务没有返回运行、分析或修复记录。请确认服务已启动。</Callout></div>
          : <>
          {failed.length > 0 && <div className="pane-body"><Callout tone="unknown" title={`${failed.join("、")}记录暂时无法读取`} actions={<button type="button" className="btn btn-sm" onClick={retry}>重试</button>}>下面只列出已读取到的记录，可能不完整。</Callout></div>}
          {items.length === 0 ? failed.length > 0 ? null : <EmptyState icon={Inbox} title="还没有记录" actions={<Link className="btn btn-primary btn-sm" href="/workspace/tasks">运行第一次复现</Link>}>复现、分析和修复的记录会出现在这里。</EmptyState>
          : <div className="table-scroll"><table className="data-table">
            <thead><tr><th scope="col" className="hide-sm">类型</th><th scope="col">内容</th><th scope="col">状态</th><th scope="col" className="hide-sm">ID</th><th scope="col" className="num">时间</th></tr></thead>
            <tbody>{items.map(item => <tr key={`${item.kind}-${item.id}`}>
              <td className="hide-sm"><span className="cell-icon subtle">{item.kind === "修复" ? <GitCompareArrows size={14} aria-hidden="true" /> : item.kind === "分析" ? <ScanSearch size={14} aria-hidden="true" /> : <Layers3 size={14} aria-hidden="true" />}{item.kind}</span></td>
              <td className="nowrap"><Link className="row-link" href={item.href}><span className="sr-only">{item.kind}：</span>{item.title}</Link></td>
              <td className="nowrap"><StatusBadge tone={item.tone}>{item.status}</StatusBadge></td>
              <td className="hide-sm"><code className="subtle small" translate="no">{shortId(item.id)}</code></td>
              <td className="num subtle nowrap"><RelativeTime value={item.at} /></td>
            </tr>)}</tbody>
          </table></div>}
          </>}
      </div>
    </section>
  </>;
}
