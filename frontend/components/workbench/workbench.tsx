"use client";
/** UI-08: 调用检查. The text sent to /api/check is exactly what is in the
 * editor (raw number literals, duplicate keys, BOM and line breaks preserved);
 * it is never parsed and re-serialised before sending. */
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { AlignLeft, FileUp, LoaderCircle, Play } from "lucide-react";
import { PageHeader } from "../ui/page-header";
import { StatusDot } from "../ui/status";
import { Kbd } from "../ui/kbd";
import { CopyButton } from "../ui/copy-id";
import { useConfirm } from "../ui/confirm-dialog";
import { useToast } from "../ui/toast";
import { useNavigationGuard } from "../ui/navigation-guard";
import { useEnvironmentStatus } from "../ui/environment-context";
import CapabilityBadge from "../capability-badge";
import { apiErrors, reportSchema, statusLabels, type Report } from "../../lib/report";
import { samples } from "../../lib/samples";
import { formatBytes, formatNumber } from "../../lib/format";
import { requestEnvironmentRefresh } from "../../lib/environment";
import { EvidenceEditor, type EvidenceEditorHandle } from "./evidence-editor";
import { CheckResult, scopeIntro } from "./check-result";
import { describeFinding } from "./describe";
import { analyzeJson, describeIssue, detectLineBreak, formatJson } from "./json-tools";

// Ephemeral tab memory preserves a draft across in-app navigation and Back/Forward only.
// It is never written to browser storage or the server.
let tabDraft: string | null = null;

const LIMIT = 1024 * 1024;
const encoder = new TextEncoder();
const bytes = (value: string) => encoder.encode(value).length;
const LEAVE = { title: "离开调用检查？", message: "编辑内容会暂存在本标签页，刷新或关闭标签页后丢失。", confirmLabel: "离开", cancelLabel: "留在此页" };
const CLI = "uv run --frozen agent-workbench check call.json";

const subscribeNothing = () => () => {};
const isMac = () => /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export default function Workbench() {
  const router = useRouter();
  const confirm = useConfirm();
  const toast = useToast();
  const env = useEnvironmentStatus();
  const [source, setSource] = useState(samples[0].value);
  const [sample, setSample] = useState<string | null>(samples[0].id);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState("");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const sourceRef = useRef(source);
  const dirtyRef = useRef(dirty);
  const editor = useRef<EvidenceEditorHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const lastLink = useRef<string | null>(null);
  const locked = busy || importing;
  const mac = useSyncExternalStore(subscribeNothing, isMac, () => true);

  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);

  useEffect(() => {
    if (tabDraft !== null) {
      sourceRef.current = tabDraft;
      setSource(tabDraft);
      setSample(null);
      setDirty(true);
    } else if (new URLSearchParams(window.location.search).get("source") === "custom") {
      sourceRef.current = "";
      setSource("");
      setSample(null);
    }
    return () => activeRequest.current?.abort();
  }, []);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => { if (dirty) tabDraft = source; }, [dirty, source]);

  // The shell's guard is synchronous and does not receive the destination, so
  // remember which same-origin link is being activated (capture phase runs
  // before the Link handler), veto the navigation, ask, then navigate ourselves.
  useEffect(() => {
    const remember = (event: MouseEvent) => {
      const link = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      lastLink.current = link && link.origin === window.location.origin ? link.pathname + link.search + link.hash : null;
    };
    document.addEventListener("click", remember, true);
    return () => document.removeEventListener("click", remember, true);
  }, []);
  useNavigationGuard(() => {
    if (!dirtyRef.current) return true;
    const href = lastLink.current;
    lastLink.current = null;
    if (!href) return window.confirm(`${LEAVE.title}${LEAVE.message}`);
    void confirm(LEAVE).then(leave => {
      if (!leave) return;
      // Close the mobile navigation drawer (the shell listens for Escape).
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      router.push(href);
    });
    return false;
  });

  const deferred = useDeferredValue(source);
  const analysis = useMemo(() => deferred.trim() ? analyzeJson(deferred) : null, [deferred]);
  const fresh = deferred === source;
  const syntaxIssue = fresh ? analysis?.issues[0] ?? null : null;
  const canFormat = fresh && analysis !== null && !analysis.issues.some(issue => issue.kind === "syntax");
  const findings = useMemo(
    () => report?.findings.map(finding => describeFinding(finding, fresh ? source : null, fresh ? analysis : null)) ?? [],
    [report, fresh, source, analysis],
  );

  const setText = useCallback((value: string) => {
    sourceRef.current = value;
    setSource(value);
    setReport(null);
    setElapsed(null);
    setNotice("");
    setSelected(null);
  }, []);

  const edit = useCallback((value: string) => {
    if (value === sourceRef.current) return;
    setText(value);
    setSample(null);
    setDirty(true);
  }, [setText]);

  async function selectSample(index: number) {
    if (locked) return;
    if (dirty && !await confirm({ title: "替换编辑器中的内容？", message: `将载入内置示例「${samples[index].label}」，未保存的修改会丢失。`, confirmLabel: "替换" })) return;
    setText(samples[index].value);
    setSample(samples[index].id);
    setDirty(false);
    tabDraft = null;
  }

  async function importFile(file: File | undefined) {
    if (!file || locked) return;
    if (file.size > LIMIT) {
      setNotice(`文件未导入：${file.name} 有 ${formatBytes(file.size)}，超过 1 MiB 上限。编辑器内容保持不变。`);
      return;
    }
    if (dirty && !await confirm({ title: "用文件替换编辑器中的内容？", message: `将导入 ${file.name}，未保存的修改会丢失。`, confirmLabel: "替换" })) return;
    setImporting(true);
    try {
      // Keep the file's exact text, including a BOM, so the checker sees the same bytes.
      const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      setText(text);
      setSample(null);
      setDirty(true);
      toast.show({ message: `已导入 ${file.name}` });
    } catch {
      setNotice(`文件未导入：${file.name} 不是 UTF-8 编码的文本。请选择 UTF-8 JSON 文件。编辑器内容保持不变。`);
    } finally {
      setImporting(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function format() {
    if (!canFormat || !analysis || locked) return;
    const formatted = formatJson(source, analysis);
    if (formatted === null || formatted === source) return;
    setText(formatted);
    setSample(null);
    setDirty(true);
  }

  async function run() {
    if (locked) return;
    const body = sourceRef.current;
    if (!body.trim()) {
      setNotice("请先粘贴或导入调用证据，或选择一个内置示例。");
      editor.current?.focus();
      return;
    }
    if (bytes(body) > LIMIT) {
      setNotice("证据超过 1 MiB。请只保留一次调用的证据后重试。");
      editor.current?.focus();
      return;
    }
    setBusy(true);
    setReport(null);
    setNotice("");
    setElapsed(null);
    setSelected(null);
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    const started = performance.now();
    try {
      // Send the editor text as-is: raw number literals and duplicate keys are judged by the Python checker.
      const response = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: controller.signal,
        cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) {
        setNotice(apiErrors[data.error] ?? `检查失败（HTTP ${response.status}）。请确认本机服务已启动，然后重试。`);
        return;
      }
      const parsed = reportSchema.safeParse(data);
      if (!parsed.success) {
        setNotice("页面与本机服务版本不一致，无法显示报告。请重启本机服务后刷新页面。");
        return;
      }
      setReport(parsed.data);
      setElapsed(Math.round(performance.now() - started));
      if (window.matchMedia("(max-width: 900px)").matches) {
        requestAnimationFrame(() => resultRef.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
      }
    } catch {
      setNotice("未能取得检查结果：连接不上本机服务。请确认本机服务已启动，然后重试。");
      requestEnvironmentRefresh();
    } finally {
      clearTimeout(timeout);
      activeRequest.current = null;
      setBusy(false);
    }
  }

  function download() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "check-report.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function locate(index: number) {
    const target = findings[index]?.target;
    if (!target) return;
    setSelected(index);
    editor.current?.reveal(target.from, target.to);
  }

  const sourceBytes = useMemo(() => bytes(deferred), [deferred]);
  const tooLarge = sourceBytes > LIMIT;
  const lineBreak = useMemo(() => detectLineBreak(deferred) === "\r\n" ? "CRLF" : "LF", [deferred]);
  const apiDown = !env.loading && !env.api.ok;
  const runShortcut = mac ? "⌘ Enter" : "Ctrl Enter";

  return <>
    <PageHeader
      title="调用检查"
      description="粘贴或导入一次工具调用的证据，检查参数和返回值是否符合工具声明的契约。"
      badge={<CapabilityBadge section="checks" />}
    />

    <div className="wb-layout">
      <section className="pane wb-editor" aria-labelledby="evidence-label">
        <div className="pane-head wb-editor-head">
          <h2 id="evidence-label">调用证据</h2>
          <div className="wb-tools">
            <button type="button" className="btn btn-sm" disabled={locked} onClick={() => fileInput.current?.click()}>
              {importing ? <LoaderCircle className="wb-spin" size={13} aria-hidden="true" /> : <FileUp size={13} aria-hidden="true" />}
              {importing ? "读取中…" : "导入文件"}
            </button>
            <input ref={fileInput} className="sr-only" type="file" accept=".json,application/json" aria-label="导入 JSON 文件" tabIndex={-1} disabled={locked}
              onChange={event => void importFile(event.target.files?.[0])} />
            <button type="button" className="btn btn-sm" disabled={locked || !canFormat} onClick={format}
              title={canFormat ? "按两个空格缩进重新排版；数字和字符串原样保留" : "JSON 有语法错误时无法格式化"}>
              <AlignLeft size={13} aria-hidden="true" />格式化
            </button>
          </div>
        </div>
        <div className="wb-samples" role="group" aria-labelledby="samples-label">
          <span id="samples-label" className="wb-samples-label">内置示例</span>
          {samples.map((item, index) => <button key={item.id} type="button" className="wb-sample" aria-pressed={sample === item.id} disabled={locked} title={item.description}
            onClick={() => void selectSample(index)}>{item.label}</button>)}
        </div>

        <EvidenceEditor
          ref={editor}
          value={source}
          disabled={locked}
          labelledBy="evidence-label"
          describedBy="evidence-status input-error"
          onChange={edit}
          onRun={() => void run()}
          onFile={file => void importFile(file)}
        />

        <div className="wb-statusbar" id="evidence-status">
          {syntaxIssue
            ? <button type="button" className="wb-issue" data-severity={syntaxIssue.severity}
              onClick={() => editor.current?.reveal(syntaxIssue.from, Math.max(syntaxIssue.to, syntaxIssue.from + 1), true)}>
              <StatusDot tone="fail" />
              <span>{describeIssue(source, syntaxIssue)}</span>
            </button>
            : <span className="wb-valid">{analysis && fresh ? "JSON 语法正确" : source.trim() ? "正在检查语法…" : "编辑器为空"}</span>}
          <span className="wb-status-meta tabular" translate="no">
            <span>UTF-8 · {lineBreak}</span>
            <span data-over={tooLarge || undefined}>{formatNumber(sourceBytes)} 字节 / 1 MiB</span>
          </span>
        </div>

        <div className="wb-editor-foot">
          <div className="wb-foot-note">
            {apiDown
              ? <span className="wb-api-note"><StatusDot tone="fail" />本机服务未连接，检查需要它在运行。</span>
              : <span className="subtle small">只在本机检查，证据不会离开这台电脑。</span>}
          </div>
          <span className="wb-shortcut subtle small" aria-hidden="true">{mac ? <Kbd>⌘</Kbd> : <Kbd>Ctrl</Kbd>}<Kbd>↵</Kbd></span>
          <button type="button" className="btn btn-primary" disabled={locked} aria-keyshortcuts={mac ? "Meta+Enter" : "Control+Enter"} title={`运行检查（${runShortcut}）`} onClick={() => void run()}>
            {busy ? <LoaderCircle className="wb-spin" size={14} aria-hidden="true" /> : <Play size={13} fill="currentColor" aria-hidden="true" />}
            {busy ? "正在检查…" : "运行检查"}
          </button>
        </div>
        <div id="input-error" className={notice ? "wb-notice" : "sr-only"} role="alert">{notice}</div>
      </section>

      <div ref={resultRef} className="wb-result-wrap">
        <CheckResult report={report} busy={busy} elapsed={elapsed} findings={findings} selected={selected} onSelect={locate} onDownload={download} />
      </div>
    </div>
    <div className="sr-only" role="status" aria-live="polite">{busy ? "正在检查…" : report ? `检查结果：${statusLabels[report.status]}` : ""}</div>

    <details className="wb-about">
      <summary>检查范围</summary>
      <div className="wb-about-body">
        <div>
          <h3>检查什么</h3>
          <ul>{scopeIntro.map(item => <li key={item.label}><strong>{item.label}</strong>：{item.text}。</li>)}</ul>
          <p>契约支持 JSON Schema 2020-12 的常用子集：type、properties、required、additionalProperties、items、enum、const、长度与数值范围、allOf / anyOf / oneOf / not。不支持 $ref、pattern、format。</p>
        </div>
        <div>
          <h3>什么时候是「未检查」或「无法判定」</h3>
          <ul>
            <li>工具没有声明 output_schema，返回结果显示「未检查」。</li>
            <li>缺少 result、工具返回了错误，或 result 与 call 的 call_id 不一致时，返回结果不再检查。</li>
            <li>证据不是有效 JSON（包括重复键和开头的 BOM）、缺少 result、契约含不支持的规则、数字可能丢失精度，或超过 1 MiB / 32 层 / 20000 个节点时，结论是「无法判定」。</li>
          </ul>
        </div>
        <div>
          <h3>在终端检查</h3>
          <p>网页和 CLI 使用同一个检查器，结果一致。在项目根目录运行（把 call.json 换成你的证据文件）：</p>
          <div className="code-block"><pre translate="no">{CLI}</pre><CopyButton value={CLI} label="命令" className="btn btn-ghost btn-sm btn-icon" /></div>
        </div>
      </div>
    </details>
  </>;
}
