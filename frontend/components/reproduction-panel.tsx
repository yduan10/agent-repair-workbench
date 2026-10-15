"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, ArrowRight, Play, RefreshCw, Square, Terminal } from "lucide-react";
import { loadRun, pollDelay, runError, RunView, scenarioLabels } from "../lib/runs";
import { loadCatalog, readinessMessage, PendingReproduction, pendingSchema, PENDING_KEY, ReproductionCatalog, ReproductionScenario, rejectionIsDefinite, saveDownload, scenarioCommand, scenarioConfig, startReproduction, submissionMessage } from "../lib/reproductions";
import { requestEnvironmentRefresh } from "../lib/environment";
import { Callout } from "./ui/callout";
import { CopyButton, CopyId } from "./ui/copy-id";
import { RelativeTime } from "./ui/relative-time";
import { Skeleton } from "./ui/skeleton";
import { StatusDot } from "./ui/status";
import { useToast } from "./ui/toast";
import type { StopState } from "./run-detail";

const SCENARIOS = ["pass", "tool_error", "timeout", "response_lost"] as const;

/** Readiness text with any shell command shown as copyable-looking code. */
function Readiness({ reason }: { reason: string | null }) {
  return <>{readinessMessage(reason).split(/(uv run [^。，]+)/).map((part, index) => index % 2 ? <code key={index} translate="no">{part}</code> : part)}</>;
}

type Props = {
  refresh: number;
  onCatalog: (value: ReproductionCatalog | null) => void;
  onBegin: () => void;
  onAccepted: (id: string, select: boolean) => void;
  /** The run occupying the web slot, when it is in the loaded list. */
  activeRun: RunView | null;
  runHref: (id: string) => string;
  onOpenRun: (id: string) => void;
  stopState?: StopState;
  /** The last stop request for the active run got no answer; stays visible until the run ends. */
  stopUnknown?: boolean;
  onStop: (id: string) => void;
};

/** The single place that launches a built-in scenario reproduction. */
export default function ReproductionPanel({ refresh, onCatalog, onBegin, onAccepted, activeRun, runHref, onOpenRun, stopState, stopUnknown, onStop }: Props) {
  const toast = useToast();
  const [catalog, setCatalog] = useState<ReproductionCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [checking, setChecking] = useState(true);
  const [checkVersion, setCheckVersion] = useState(0);
  const [scenario, setScenario] = useState<ReproductionScenario>("pass");
  const [pending, setPending] = useState<PendingReproduction | null>(null);
  const [phase, setPhase] = useState<"idle" | "submitting" | "unknown">("idle");
  const [rejection, setRejection] = useState("");
  const [unknownNotice, setUnknownNotice] = useState("");
  const [lookupNotice, setLookupNotice] = useState("");
  const [lookupVersion, setLookupVersion] = useState(0);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [storageNotice, setStorageNotice] = useState("");
  const writing = useRef(false);
  const writeController = useRef<AbortController | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    try {
      const raw = sessionStorage.getItem(PENDING_KEY);
      if (raw && raw.length <= 300) {
        const parsed = pendingSchema.safeParse(JSON.parse(raw));
        if (parsed.success) { setPending(parsed.data); setScenario(parsed.data.scenario); setPhase("unknown"); setUnknownNotice("无法确认上次提交是否已开始，正在查询（不会重新运行）。"); }
      }
    } catch { setStorageNotice("浏览器禁用了会话存储。提交后如果刷新页面，将无法自动找回这次提交。"); }
    return () => { alive.current = false; writeController.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setChecking(true);
    async function read() {
      try {
        const value = await loadCatalog(controller.signal);
        if (controller.signal.aborted) return;
        setCatalog(value); onCatalog(value); setCatalogError(""); setChecking(false);
        if (value.active_run_id) { await pollDelay(2000, controller.signal); if (!controller.signal.aborted) void read(); }
      } catch (error) {
        if (!controller.signal.aborted) { setCatalog(null); onCatalog(null); setCatalogError(runError(error)); setChecking(false); }
      }
    }
    void read();
    return () => controller.abort();
  }, [refresh, checkVersion, onCatalog]);

  useEffect(() => {
    if (!pending || phase !== "unknown") return;
    const controller = new AbortController();
    setLookupBusy(true); setLookupNotice("");
    loadRun(pending.request_id, controller.signal).then(detail => {
      if (controller.signal.aborted) return;
      if (detail.run.scenario !== pending.scenario) { setLookupNotice("查到的运行与本次提交的场景不同，可能是服务数据异常。反馈问题时请附上请求 ID。"); return; }
      clearPending(); toast.show({ tone: "pass", message: "已找到这次提交的运行记录。" });
      onAccepted(detail.run.run_id, false);
    }).catch(() => {
      if (!controller.signal.aborted) setLookupNotice("还没查到这次提交的运行。服务可能仍在处理，请过几秒再查询。");
    }).finally(() => { if (!controller.signal.aborted) setLookupBusy(false); });
    return () => controller.abort();
  }, [pending, phase, lookupVersion, onAccepted, toast]);

  function clearPending() {
    try { sessionStorage.removeItem(PENDING_KEY); } catch { /* Keep runtime state even when storage is unavailable. */ }
    setPending(null); setPhase("idle");
  }
  async function start() {
    if (writing.current || pending || !catalog?.ready || catalog.active_run_id) return;
    writing.current = true; onBegin();
    const request = { request_id: crypto.randomUUID(), scenario };
    setPending(request); setPhase("submitting"); setRejection(""); setUnknownNotice(""); setLookupNotice("");
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify(request)); }
    catch { setStorageNotice("浏览器禁用了会话存储。提交后如果刷新页面，将无法自动找回这次提交。"); }
    const controller = new AbortController(); writeController.current = controller;
    try {
      const result = await startReproduction(request, controller.signal);
      if (!alive.current) return;
      clearPending();
      toast.show({ tone: "pass", message: result.reused ? "已找到这次提交的运行，没有重复运行。" : `复现已开始：${scenarioLabels[request.scenario]}` });
      onAccepted(result.run.run_id, true); setCheckVersion(value => value + 1); requestEnvironmentRefresh();
    } catch (error) {
      if (!alive.current) return;
      const message = submissionMessage(error);
      if (rejectionIsDefinite(error)) { clearPending(); setRejection(message); } else { setPhase("unknown"); setUnknownNotice(message); }
      setCheckVersion(value => value + 1);
    } finally { writing.current = false; }
  }

  const selectedCase = catalog?.cases.find(item => item.id === scenario);
  const activeId = catalog?.active_run_id ?? null;
  const busyElsewhere = catalog && !catalog.ready && catalog.reason === "runner_busy" && !activeId;
  const blocked = !catalog ? (catalogError ? "场景列表不可用，见上方说明。" : "正在检查环境…")
    : activeId ? "已有复现在运行，结束后才能开始新的复现。"
    : !catalog.ready ? "本机还不能运行复现，见上方说明。"
    : pending ? "上次提交尚未确认，请先查询提交结果。" : "";
  const recheck = <button type="button" className="btn btn-sm" onClick={() => setCheckVersion(value => value + 1)} disabled={checking}><RefreshCw size={13} aria-hidden="true" />{checking ? "检查中…" : "重新检查环境"}</button>;

  return <section className="launcher" aria-labelledby="launcher-heading">
    <div className="launcher-main">
      <div className="launcher-pick">
        <div className="launcher-title">
          <h2 id="launcher-heading">新建复现</h2>
          <span className="small subtle">内置示例 · 容器断网、只读、非 root，并限制资源</span>
        </div>
        <fieldset className="segmented" disabled={phase !== "idle" || !catalog}>
          <legend className="sr-only">选择场景</legend>
          {SCENARIOS.map(id => <label key={id} data-checked={scenario === id || undefined}>
            <input type="radio" name="reproduction-scenario" value={id} checked={scenario === id} onChange={() => { setScenario(id); setRejection(""); }} />
            <span>{scenarioLabels[id]}</span>
          </label>)}
        </fieldset>
        <p className="launcher-desc" aria-live="polite">
          {selectedCase ? <><span>{selectedCase.description}</span> <span className="launcher-expected"><span className="subtle">预期</span> {selectedCase.expected}</span></>
            : catalogError ? <span className="subtle">场景说明不可用。</span>
            : <span className="launcher-desc-skeleton" aria-hidden="true"><Skeleton width={320} height={11} /></span>}
        </p>
      </div>
      <div className="launcher-go">
        <button type="button" className="btn btn-primary btn-lg" onClick={() => void start()} disabled={phase !== "idle" || !catalog?.ready || !!activeId || !!pending}
          aria-describedby={blocked ? "launcher-blocked" : undefined} aria-busy={phase === "submitting" || undefined}>
          <Play size={14} aria-hidden="true" />{phase === "submitting" ? "正在提交…" : "开始复现"}
        </button>
        {blocked && phase === "idle" && <span id="launcher-blocked" className="sr-only">{blocked}</span>}
      </div>
    </div>

    {activeId && <div className="launcher-active" id="launcher-active" tabIndex={-1}>
      <StatusDot tone="running" />
      <span className="launcher-active-text">
        {/* Only the state is a live region; the relative time ticks every 30 s and must not be re-announced. */}
        <span className="launcher-active-state" role="status">
          <strong>{activeRun ? scenarioLabels[activeRun.scenario] : "一项复现"}</strong>
          <span>{stopState === "requested" ? "正在停止…" : "正在运行"}</span>
        </span>
        {activeRun && <span className="subtle">· 开始于 <RelativeTime value={activeRun.created_at} /></span>}
      </span>
      <span className="launcher-active-actions">
        <a className="btn btn-sm btn-ghost" href={runHref(activeId)} onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return; event.preventDefault(); onOpenRun(activeId); }}>查看运行<ArrowRight size={13} aria-hidden="true" /></a>
        <button type="button" className="btn btn-sm btn-danger" disabled={!!stopState} onClick={() => onStop(activeId)}><Square size={12} aria-hidden="true" />{stopState ? "正在停止…" : "停止"}</button>
      </span>
      {stopUnknown && !stopState && <p className="launcher-active-note" role="alert">无法确认是否已停止。运行状态以下方记录为准，必要时再点一次「停止」。</p>}
    </div>}

    {(catalogError || (catalog && !catalog.ready && !activeId) || rejection || (pending && phase === "unknown") || storageNotice) && <div className="launcher-notes">
      {catalogError && <Callout tone="fail" title="无法检查复现环境" role="alert" actions={recheck}>{catalogError}</Callout>}
      {catalog && !catalog.ready && !activeId && (busyElsewhere
        ? <Callout tone="neutral" title="执行槽占用中" actions={recheck}><Readiness reason={catalog.reason} /></Callout>
        : <Callout tone="unknown" title="本机还不能运行复现" role="status" actions={recheck}><Readiness reason={catalog.reason} /></Callout>)}
      {rejection && <Callout tone="fail" title="没有开始复现" role="alert">{rejection}</Callout>}
      {pending && phase === "unknown" && <Callout tone="unknown" title="无法确认复现是否已开始"
        actions={<button type="button" className="btn btn-sm" disabled={lookupBusy} onClick={() => setLookupVersion(value => value + 1)} aria-busy={lookupBusy || undefined}>{lookupBusy ? "正在查询…" : "查询提交结果"}</button>}>
        <p role="status">{unknownNotice}</p>
        {lookupNotice && <p role="status">{lookupNotice}</p>}
        <p className="launcher-request small">请求 ID <CopyId value={pending.request_id} label="请求 ID" /> 刷新或离开页面不会停止运行。</p>
      </Callout>}
      {storageNotice && <Callout tone="unknown">{storageNotice}</Callout>}
    </div>}

    <details className="launcher-cli">
      <summary><Terminal size={13} aria-hidden="true" />在终端运行</summary>
      <ol className="launcher-steps">
        <li><span>下载场景配置，放到项目根目录。</span>
          <button type="button" className="btn btn-sm" onClick={() => saveDownload(JSON.stringify(scenarioConfig(scenario), null, 2) + "\n", `awb-${scenario}-server.json`)}>
            <ArrowDownToLine size={13} aria-hidden="true" />下载场景配置<code translate="no" className="subtle">awb-{scenario}-server.json</code>
          </button>
        </li>
        <li><span>在项目根目录运行：</span>
          <div className="code-block"><pre translate="no">{scenarioCommand(scenario)}</pre><CopyButton value={scenarioCommand(scenario)} label="命令" className="btn btn-sm btn-ghost">复制</CopyButton></div>
        </li>
      </ol>
      <p className="small subtle">CLI 运行也会出现在下方运行记录中。首次使用前需要初始化数据库并准备镜像，见 <Link className="link" href="/docs/27-local-development-guide">本地开发指南</Link>。</p>
    </details>
  </section>;
}
