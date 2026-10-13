"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDownToLine, Copy, Play, RefreshCw } from "lucide-react";
import { loadRun, runError, scenarioLabels } from "../lib/runs";
import { loadCatalog, readinessMessage, PendingReproduction, pendingSchema, PENDING_KEY, ReproductionCatalog, ReproductionScenario, rejectionIsDefinite, saveDownload, scenarioCommand, scenarioConfig, startReproduction, submissionMessage } from "../lib/reproductions";

type Props = { refresh: number; onCatalog: (value: ReproductionCatalog | null) => void; onBegin: () => void; onAccepted: (id: string, select: boolean) => void; onSelect: (id: string) => void };

export default function ReproductionPanel({ refresh, onCatalog, onBegin, onAccepted, onSelect }: Props) {
  const [catalog, setCatalog] = useState<ReproductionCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [checking, setChecking] = useState(true);
  const [checkVersion, setCheckVersion] = useState(0);
  const [scenario, setScenario] = useState<ReproductionScenario>("pass");
  const [pending, setPending] = useState<PendingReproduction | null>(null);
  const [phase, setPhase] = useState<"idle" | "submitting" | "unknown">("idle");
  const [notice, setNotice] = useState("");
  const [lookupNotice, setLookupNotice] = useState("");
  const [lookupVersion, setLookupVersion] = useState(0);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [copyNotice, setCopyNotice] = useState("");
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
        if (parsed.success) { setPending(parsed.data); setScenario(parsed.data.scenario); setPhase("unknown"); setNotice("发现上次尚未确认的提交。只查询已有结果，不重新执行。"); }
      }
    } catch { setStorageNotice("当前浏览器无法保留请求标识；离页前请保存下方技术信息。"); }
    return () => { alive.current = false; writeController.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setChecking(true);
    async function read() {
      try {
        const value = await loadCatalog(controller.signal);
        if (controller.signal.aborted) return;
        setCatalog(value); onCatalog(value); setCatalogError("");
        if (value.active_run_id) timer = setTimeout(() => void read(), 2000);
      } catch (error) {
        if (!controller.signal.aborted) { setCatalog(null); onCatalog(null); setCatalogError(runError(error)); }
      } finally { if (!controller.signal.aborted) setChecking(false); }
    }
    void read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [refresh, checkVersion, onCatalog]);

  useEffect(() => {
    if (!pending || phase !== "unknown") return;
    const controller = new AbortController();
    setLookupBusy(true); setLookupNotice("");
    loadRun(pending.request_id, controller.signal).then(detail => {
      if (controller.signal.aborted) return;
      if (detail.run.scenario !== pending.scenario) { setLookupNotice("记录场景与本次提交不一致，请保留请求标识并核对服务。"); return; }
      clearPending(); setNotice("已找到本次提交的运行记录。可在最近运行中查看结果。");
      onAccepted(detail.run.run_id, false);
    }).catch(() => {
      if (!controller.signal.aborted) setLookupNotice("暂未确认本次提交。请稍后继续查询；查不到记录也不能推断未执行。");
    }).finally(() => { if (!controller.signal.aborted) setLookupBusy(false); });
    return () => controller.abort();
  }, [pending, phase, lookupVersion, onAccepted]);

  function clearPending() {
    try { sessionStorage.removeItem(PENDING_KEY); } catch { /* Keep runtime state even when storage is unavailable. */ }
    setPending(null); setPhase("idle");
  }
  async function start() {
    if (writing.current || pending || !catalog?.ready || catalog.active_run_id) return;
    writing.current = true; onBegin();
    const request = { request_id: crypto.randomUUID(), scenario };
    setPending(request); setPhase("submitting"); setNotice(""); setLookupNotice("");
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify(request)); }
    catch { setStorageNotice("请求标识未能保存至浏览器。离页前请保存下方技术信息；刷新后不要直接新建同一任务。"); }
    const controller = new AbortController(); writeController.current = controller;
    try {
      const result = await startReproduction(request, controller.signal);
      if (!alive.current) return;
      clearPending(); setNotice(result.reused ? "已找到此请求的原运行，没有重复执行。" : "复现已接收。进度与结果以服务端记录为准。");
      onAccepted(result.run.run_id, true); setCheckVersion(value => value + 1);
    } catch (error) {
      if (!alive.current) return;
      setNotice(submissionMessage(error));
      if (rejectionIsDefinite(error)) clearPending(); else setPhase("unknown");
      setCheckVersion(value => value + 1);
    } finally { writing.current = false; }
  }
  const selectedCase = catalog?.cases.find(item => item.id === scenario);
  return <section className="reproduction-panel" aria-labelledby="reproduction-heading">
    <div className="reproduction-heading"><div><h2 id="reproduction-heading">新建受控复现</h2><p>选择一种故障，在本机隔离容器中验证工具调用。</p></div><span className="reproduction-scope">4 种固定场景</span></div>
    <fieldset className="scenario-picker" disabled={phase !== "idle" || !catalog}>
      <legend className="sr-only">选择复现场景</legend>
      {(["pass", "tool_error", "timeout", "response_lost"] as const).map(id => <label key={id} className={scenario === id ? "chosen" : ""}><input type="radio" name="reproduction-scenario" value={id} checked={scenario === id} onChange={() => { setScenario(id); setCopyNotice(""); }} /><span>{scenarioLabels[id]}</span></label>)}
    </fieldset>
    <div className="scenario-explanation" aria-live="polite">{selectedCase ? <><p>{selectedCase.description}</p><p><strong>预期结果</strong> {selectedCase.expected}</p></> : <p>正在等待本机服务提供已审核的场景说明。</p>}</div>
    <p className="reproduction-boundary">已审核的合成故障场景；执行与状态是真实记录。固定 lookup 用例，断网、非 root、只读与资源限额；不接收任意代码或命令。</p>
    {catalogError && <p className="reproduction-error" role="alert">{catalogError}</p>}
    {catalog && !catalog.ready && <p className="reproduction-error" role="status">{readinessMessage(catalog.reason)}<Link href="/docs">查看准备说明</Link></p>}
    {catalog?.active_run_id && <p className="reproduction-busy">网页执行槽已占用。<button className="text-link" onClick={() => onSelect(catalog.active_run_id!)}>查看当前运行</button></p>}
    <div className="reproduction-actions"><button className="reproduction-start" onClick={() => void start()} disabled={phase !== "idle" || !catalog?.ready || !!catalog?.active_run_id}><Play size={15} aria-hidden="true" />{phase === "submitting" ? "正在提交…" : "开始复现"}</button><button className="download" onClick={() => setCheckVersion(value => value + 1)} disabled={checking}><RefreshCw size={14} aria-hidden="true" />{checking ? "检查中…" : "重新检查准备状态"}</button></div>
    <p className="reproduction-notice" role="status">{notice}</p>
    {pending && phase === "unknown" && <div className="reproduction-uncertain"><button className="download" disabled={lookupBusy} onClick={() => setLookupVersion(value => value + 1)}>{lookupBusy ? "正在查询…" : "仅查询提交结果"}</button><p role="status">{lookupNotice}</p></div>}
    {storageNotice && <p className="run-note">{storageNotice}</p>}
    {pending && <details className="reproduction-request"><summary>本次请求技术信息</summary><code>{pending.request_id}</code><p>刷新或离页不会停止服务端任务。请用此标识查询结果。</p></details>}
    <details className="reproduction-cli"><summary>在终端运行此场景</summary><p>这是同场景的新运行，不是重放旧记录。先在<strong>项目根目录</strong>准备环境，将下载的 <code>awb-{scenario}-server.json</code> 放到根目录，再复制命令。</p><pre tabIndex={0} role="region" aria-label="复现命令"><code>{scenarioCommand(scenario)}</code></pre><div className="reproduction-actions"><button className="download" onClick={() => saveDownload(JSON.stringify(scenarioConfig(scenario), null, 2) + "\n", `awb-${scenario}-server.json`)}><ArrowDownToLine size={14} aria-hidden="true" />下载场景配置</button><button className="download" onClick={async () => { try { await navigator.clipboard.writeText(scenarioCommand(scenario)); setCopyNotice("命令已复制。"); } catch { setCopyNotice("无法访问剪贴板，请从上方命令区手动复制。"); } }}><Copy size={14} aria-hidden="true" />复制命令</button></div><p role="status">{copyNotice}</p><p>固定用例：<code>examples/mcp/lookup-case.json</code>（lookup，id=1）。CLI 也写入本机运行记录。</p><Link href="/docs">查看初始化与镜像准备步骤</Link></details>
  </section>;
}
