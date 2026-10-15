"use client";
import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { useEnvironmentStatus } from "../ui/environment-context";
import { StatusBadge, StatusDot } from "../ui/status";
import { RelativeTime } from "../ui/relative-time";
import { SkeletonRows } from "../ui/skeleton";
import { readinessMessage } from "../../lib/reproductions";
import { Command, EnvSection, SettingRow } from "./section";
import { apiAddress, commands, docs } from "./commands";

/** Plain fix text per readiness reason; the command (if any) is shown below it. */
const runnerFixes: Record<string, { text: string; command?: string }> = {
  docker_unavailable: { text: "Docker 没有运行。启动 Docker（macOS 可用 Colima）后点击「重新检查」。" },
  image_not_prepared: { text: "固定镜像还没有准备。在项目根目录运行下面的命令，完成后点击「重新检查」。网页不会自动构建或下载镜像。", command: commands.prepareImage },
  store_not_initialized: { text: "记录库还没有创建。在项目根目录运行下面的命令。", command: commands.runsInit },
  schema_incompatible: { text: "记录库版本与本机服务不一致。先停止写入并备份记录目录，再运行下面的命令升级。", command: commands.runsInit },
  store_unavailable: { text: "无法打开记录库。检查记录目录是否存在且可写，然后重新检查。" },
  locking_unavailable: { text: "本机执行锁不可用。检查本机服务状态后重新检查。" },
};

export function StatusSection() {
  const env = useEnvironmentStatus();
  const firstLoad = env.checkedAt === null;
  const reproduction = env.reproduction;
  const analysis = env.analysis;
  const runnerBusy = reproduction?.reason === "runner_busy";
  const runnerReady = !!reproduction && (reproduction.ready || runnerBusy);
  const fix = reproduction && !runnerReady ? runnerFixes[reproduction.reason ?? ""] ?? { text: readinessMessage(reproduction.reason) } : null;
  const offline = !env.api.ok;
  const needsApi = <span className="subtle">连接本机服务后显示。</span>;

  return <EnvSection id="status" title="本机环境" description="网页依赖的本机服务、复现环境和执行槽。每 15 秒自动检查一次。"
    actions={<>
      <span className="muted small">{env.checkedAt ? <>检查于 <RelativeTime value={env.checkedAt} /></> : "正在检查…"}</span>
      <button type="button" className="btn btn-sm" onClick={env.refresh}><RefreshCw size={13} aria-hidden="true" />重新检查</button>
    </>}>
    <div className="pane env-pane" aria-busy={firstLoad}>
      {firstLoad ? <SkeletonRows rows={3} label="正在检查本机环境…" /> : <>
        <SettingRow label="本机服务" aside={<StatusBadge tone={offline ? "fail" : "pass"}>{offline ? "未连接" : "已连接"}</StatusBadge>}>
          <dl className="env-facts">
            <div><dt>地址</dt><dd><code translate="no">{apiAddress}</code></dd></div>
            {env.api.checkerVersion && <div><dt>检查器</dt><dd><code translate="no">{env.api.checkerVersion}</code></dd></div>}
          </dl>
          {offline && <div className="env-fix">
            <p>页面无法连接本机服务。在项目根目录运行下面的命令启动服务，然后点击「重新检查」。</p>
            <Command value={commands.startApi} label="启动命令" />
          </div>}
        </SettingRow>

        <SettingRow label="复现环境" aside={offline ? undefined : !reproduction ? <StatusBadge tone="unknown">无法读取</StatusBadge>
          : runnerBusy ? <StatusBadge tone="running">运行中</StatusBadge>
          : <StatusBadge tone={runnerReady ? "pass" : "unknown"}>{runnerReady ? "就绪" : "未就绪"}</StatusBadge>}>
          {offline ? needsApi : !reproduction ? <p className="muted">场景目录读取失败。确认本机服务与网页版本一致后重新检查。</p> : <>
            <p className="muted">{runnerBusy ? "正在运行一项复现，结束后可开始新的复现。" : `Docker 与固定执行镜像${runnerReady ? "已就绪，可以运行复现。" : "还不可用，暂时无法运行复现。"}`}</p>
            {fix ? <div className="env-fix">
              <p>{fix.text}</p>
              {fix.command && <Command value={fix.command} label="命令" />}
            </div> : <details className="env-more">
              <summary>重新准备镜像</summary>
              <p className="muted small">镜像源码或运行配置修改后，需要重新准备。</p>
              <Command value={commands.prepareImage} label="准备命令" />
            </details>}
          </>}
        </SettingRow>

        <SettingRow label="执行槽">
          {offline ? needsApi : <ul className="env-slots">
            <li>
              <StatusDot tone={!reproduction ? "unknown" : reproduction.active_run_id ? "running" : "pass"} />
              <span className="env-slot-name">复现</span>
              <span className="muted">{!reproduction ? "无法读取" : reproduction.active_run_id ? "正在运行" : "空闲"}</span>
              {reproduction?.active_run_id && <Link className="link small env-slot-link" href={`/workspace/tasks?run=${reproduction.active_run_id}`}>查看运行<ArrowRight size={12} aria-hidden="true" /></Link>}
            </li>
            <li>
              <StatusDot tone={!analysis ? "unknown" : analysis.slot.status === "available" ? "pass" : analysis.slot.status === "busy" ? "running" : "fail"} />
              <span className="env-slot-name">分析</span>
              <span className="muted">{!analysis ? "无法读取" : analysis.slot.status === "available" ? "空闲" : analysis.slot.status === "busy" ? "正在分析" : "需要恢复"}</span>
              {analysis?.slot.status === "busy" && analysis.slot.task_id && <Link className="link small env-slot-link" href={`/workspace/diagnosis?analysis=${analysis.slot.task_id}`}>查看分析<ArrowRight size={12} aria-hidden="true" /></Link>}
            </li>
          </ul>}
          {analysis?.slot.status === "recovery_required" && analysis.slot.task_id && <div className="env-fix">
            <p>上次分析在本机服务退出时中断。运行下面的命令核对这条分析，完成后才能发起新分析。不会重新调用模型或工具。</p>
            <Command value={commands.analysesReconcile(analysis.slot.task_id)} label="核对命令" />
            <Link className="link small" href={docs.records}>运行记录与恢复说明</Link>
          </div>}
          {!offline && <p className="subtle small env-slot-note">复现和分析各有一个执行槽，同一时间各运行一项。</p>}
        </SettingRow>
      </>}
    </div>
  </EnvSection>;
}
