"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Braces,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  CircleX,
  FileJson2,
  FlaskConical,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Play,
  ShieldCheck,
  Terminal,
  Upload,
  Workflow,
} from "lucide-react";
import {
  apiErrors,
  checkLabels,
  findingLabels,
  Report,
  reportSchema,
  statusLabels,
} from "../../lib/report";
import Sidebar from "../../components/sidebar";
import WorkspaceFooter from "../../components/workspace-footer";
import { samples } from "../../lib/samples";

// Ephemeral tab memory preserves a draft across browser Back/Forward only.
// It is never written to browser storage or the server.
let tabDraft: string | null = null;

const LIMIT = 1024 * 1024;
const bytes = (value: string) => new TextEncoder().encode(value).length;
const number = new Intl.NumberFormat("zh-CN");

export default function Workbench() {
  const [source, setSource] = useState(samples[0].value);
  const [sample, setSample] = useState<string | null>(samples[0].id);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState("");
  const [api, setApi] = useState<"loading" | "online" | "offline">("loading");
  const [openFinding, setOpenFinding] = useState(0);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const locked = busy || importing;

  async function health() {
    setApi("loading");
    try {
      const response = await fetch("/api/health", {
        cache: "no-store",
        signal: AbortSignal.timeout(3000),
      });
      const data = await response.json();
      setApi(response.ok && data.status === "ok" ? "online" : "offline");
    } catch {
      setApi("offline");
    }
  }
  useEffect(() => {
    void health();
    if (tabDraft !== null) {
      setSource(tabDraft);
      setSample(null);
      setDirty(true);
    } else if (
      new URLSearchParams(window.location.search).get("source") === "custom"
    ) {
      setSource("");
      setSample(null);
    }
    return () => activeRequest.current?.abort();
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (dirty) tabDraft = source;
  }, [dirty, source]);

  function replaceSource(value: string, id: string | null) {
    setSource(value);
    setSample(id);
    setReport(null);
    setElapsed(null);
    setNotice("");
  }
  function selectSample(index: number) {
    if (dirty && !window.confirm("替换当前尚未保存的证据内容？")) return;
    replaceSource(samples[index].value, samples[index].id);
    setDirty(false);
    tabDraft = null;
  }
  async function importFile(file: File | undefined) {
    if (!file || locked) return;
    if (file.size > LIMIT) {
      setNotice("文件未导入：超过 1 MiB。当前证据与报告保持不变。");
      return;
    }
    if (dirty && !window.confirm("用文件内容替换当前尚未保存的证据？")) return;
    setImporting(true);
    try {
      const text = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(await file.arrayBuffer());
      replaceSource(text, null);
      setDirty(true);
    } catch {
      setNotice("文件未导入：请选择 UTF-8 JSON。当前证据与报告保持不变。");
    } finally {
      setImporting(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  async function run() {
    if (locked) return;
    if (!source.trim()) {
      setNotice("请先导入证据，或选择一个合成示例。");
      editor.current?.focus();
      return;
    }
    if (bytes(source) > LIMIT) {
      setNotice("证据超过 1 MiB，请缩小内容后重试。");
      editor.current?.focus();
      return;
    }
    setBusy(true);
    setReport(null);
    setNotice("");
    setElapsed(null);
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    const started = performance.now();
    try {
      // Preserve raw number literals and duplicate keys for the Python checker.
      const response = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: source,
        signal: controller.signal,
        cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) {
        setNotice(
          apiErrors[data.error] ??
            "检查服务暂时不可用，请确认本地 API 已启动后重试。",
        );
        return;
      }
      const parsed = reportSchema.safeParse(data);
      if (!parsed.success) {
        setNotice("服务返回的报告格式不受支持，请核对前后端版本后重试。");
        return;
      }
      setReport(parsed.data);
      setOpenFinding(0);
      setElapsed(Math.round(performance.now() - started));
      setApi("online");
    } catch {
      setNotice("未能取得检查结果，请确认本地 API 已启动，然后重试。");
      setApi("offline");
    } finally {
      clearTimeout(timeout);
      activeRequest.current = null;
      setBusy(false);
    }
  }
  function download() {
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "check-report.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function beforeNavigate() {
    return !dirty || window.confirm(
      "离开此页？未保存的草稿仅在当前标签页内临时保留，刷新或关闭后会丢失。",
    );
  }

  const sourceBytes = bytes(source);
  return (
    <div className="shell">
      <a className="skip" href="#main">
        跳至工作台
      </a>
      <Sidebar beforeNavigate={beforeNavigate} />

      <main id="main">
        <header className="topbar">
          <div className="breadcrumb">
            <Layers3 size={16} aria-hidden="true" />
            <span>工作区</span>
            <ChevronRight size={13} aria-hidden="true" />
            <strong>调用检查</strong>
          </div>
          <button
            className={`connection ${api}`}
            onClick={() => void health()}
            aria-label="重新检查本地 API 连接"
          >
            <span />
            {api === "online"
              ? "本地 API 已连接"
              : api === "offline"
                ? "本地 API 未连接"
                : "正在连接…"}
          </button>
        </header>
        <div className="main-content">
          <section className="intro" id="workspace">
            <div>
              <div className="intro-label">
                <span className="tiny-bracket">[✓]</span>工具调用检查
              </div>
              <h1>每一次调用，都有据可查。</h1>
              <p>放入调用证据，核对参数与结果，找到不符合契约的位置。</p>
            </div>
            <a className="text-link" href="#testing">
              了解检查范围 <ArrowUpRight size={15} aria-hidden="true" />
            </a>
          </section>

          <section className="sample-strip" aria-label="合成示例">
            <div className="sample-heading">
              <FlaskConical size={17} aria-hidden="true" />
              <span>
                从一个示例开始<small>合成数据，可直接体验</small>
              </span>
            </div>
            <div className="sample-options">
              {samples.map((item, index) => (
                <button
                  key={item.id}
                  disabled={locked}
                  aria-pressed={sample === item.id}
                  className={`sample-option ${sample === item.id ? "selected" : ""}`}
                  onClick={() => selectSample(index)}
                >
                  <span className={`sample-dot sample-${item.id}`} />
                  <span>{item.label}</span>
                  {sample === item.id && <Check size={14} aria-hidden="true" />}
                </button>
              ))}
            </div>
          </section>

          <div className="work-area">
            <section
              className="evidence-panel"
              aria-labelledby="evidence-label"
            >
              <div className="panel-heading">
                <div className="panel-title">
                  <FileJson2 size={18} aria-hidden="true" />
                  <label id="evidence-label" htmlFor="evidence">
                    调用证据
                  </label>
                  <span className="muted-tag">JSON</span>
                </div>
                <button
                  className="import-button"
                  disabled={locked}
                  onClick={() => fileInput.current?.click()}
                >
                  <Upload size={14} aria-hidden="true" />
                  {importing ? "读取中…" : "导入文件"}
                </button>
                <input
                  ref={fileInput}
                  className="sr-only"
                  type="file"
                  accept=".json,application/json"
                  aria-label="导入 JSON 文件"
                  disabled={locked}
                  onChange={(event) => void importFile(event.target.files?.[0])}
                />
              </div>
              <div className="editor-meta">
                <span>
                  <i />
                  {sample ? "合成示例" : "自定义证据"}
                </span>
                <span>UTF-8</span>
              </div>
              <textarea
                id="evidence"
                name="evidence"
                ref={editor}
                value={source}
                disabled={locked}
                spellCheck={false}
                autoComplete="off"
                wrap="off"
                aria-describedby="evidence-help input-error"
                onChange={(event) => {
                  replaceSource(event.target.value, null);
                  setDirty(true);
                }}
                placeholder={'粘贴完整调用证据，例如 {"schema_version": 1, …}'}
              />
              <div className="editor-status">
                <span>{number.format(sourceBytes)} bytes</span>
                <span>单次证据上限 1 MiB</span>
              </div>
              <div className="editor-action">
                <p id="evidence-help">
                  <ShieldCheck size={14} aria-hidden="true" />
                  仅在本机检查
                </p>
                <button
                  className="primary"
                  disabled={locked}
                  onClick={() => void run()}
                >
                  {busy ? (
                    <LoaderCircle
                      className="spin"
                      size={16}
                      aria-hidden="true"
                    />
                  ) : (
                    <Play size={15} fill="currentColor" aria-hidden="true" />
                  )}
                  {busy ? "正在检查…" : "运行检查"}
                </button>
              </div>
              <div
                id="input-error"
                className={notice ? "input-error" : "sr-only"}
                role="alert"
              >
                {notice}
              </div>
            </section>

            <section
              className="results-panel"
              aria-labelledby="result-title"
              aria-busy={busy}
            >
              <div className="panel-heading">
                <div className="panel-title">
                  <CheckCheck size={18} aria-hidden="true" />
                  <h2 id="result-title">检查结果</h2>
                </div>
                <span className="result-meta">
                  {elapsed !== null
                    ? `${number.format(elapsed)} ms`
                    : "等待运行"}
                </span>
              </div>
              <div
                className="live-summary sr-only"
                role="status"
                aria-live="polite"
              >
                {busy
                  ? "检查正在进行"
                  : report
                    ? statusLabels[report.status]
                    : "尚未运行检查"}
              </div>
              {!report ? (
                <div className={`empty-result ${busy ? "is-loading" : ""}`}>
                  <div className="empty-visual" aria-hidden="true">
                    <div className="document-shape">
                      <span />
                      <span />
                      <span />
                      <div className="document-check">
                        {busy ? (
                          <LoaderCircle className="spin" size={20} />
                        ) : (
                          <Check size={20} />
                        )}
                      </div>
                    </div>
                  </div>
                  <h3>
                    {busy ? "正在核对这次调用…" : "运行检查后，在这里查看结果"}
                  </h3>
                  <p>
                    {busy
                      ? "检查完成后，结果与依据会出现在这里。"
                      : "先选择示例或导入 JSON，再点击「运行检查」。结果会列出检查范围、不符合项与字段路径。"}
                  </p>
                  <div className="empty-capabilities">
                    <span>
                      <Check size={13} aria-hidden="true" />
                      参数契约
                    </span>
                    <span>
                      <Check size={13} aria-hidden="true" />
                      返回结果
                    </span>
                    <span>
                      <Check size={13} aria-hidden="true" />
                      调用关联
                    </span>
                  </div>
                </div>
              ) : (
                <div
                  className="report-body"
                  key={report.evidence_sha256 ?? report.status}
                >
                  <div className={`outcome ${report.status}`}>
                    <div className="outcome-icon" aria-hidden="true">
                      {report.status === "passed" ? (
                        <CheckCheck size={24} />
                      ) : report.status === "failed" ? (
                        <CircleX size={24} />
                      ) : (
                        <CircleHelp size={24} />
                      )}
                    </div>
                    <div>
                      <h3>{statusLabels[report.status]}</h3>
                      <p>
                        {report.status === "passed"
                          ? "已声明且支持的检查均已通过。"
                          : report.status === "failed"
                            ? "存在明确的不符合项，请查看下方依据。"
                            : "当前证据或支持范围不足，未作通过判断。"}
                      </p>
                    </div>
                  </div>
                  <div className="coverage">
                    <div>
                      <span>输入参数</span>
                      <span className={`check-state ${report.checks.input}`}>
                        {checkLabels[report.checks.input]}
                      </span>
                    </div>
                    <div>
                      <span>返回结果</span>
                      <span className={`check-state ${report.checks.output}`}>
                        {checkLabels[report.checks.output]}
                      </span>
                    </div>
                  </div>
                  <div className="findings-header">
                    <h3>检查依据</h3>
                    <span>
                      {report.findings.length
                        ? `${report.findings_truncated ? "前 " : ""}${report.findings.length} 项`
                        : "无不符合项"}
                    </span>
                  </div>
                  <div className="findings">
                    {report.findings.map((finding, index) => {
                      const description = findingLabels[finding.code] ?? [
                        "检查未完成",
                        "请根据错误代码核对检查器支持范围。",
                      ];
                      return (
                        <div
                          className="finding"
                          key={`${finding.code}-${index}`}
                        >
                          <button
                            aria-expanded={openFinding === index}
                            aria-controls={`finding-${index}`}
                            onClick={() =>
                              setOpenFinding(openFinding === index ? -1 : index)
                            }
                          >
                            <span className="finding-index">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <strong>{description[0]}</strong>
                            <ChevronDown
                              size={16}
                              className={
                                openFinding === index ? "expanded" : ""
                              }
                              aria-hidden="true"
                            />
                          </button>
                          {openFinding === index && (
                            <div
                              className="finding-detail"
                              id={`finding-${index}`}
                            >
                              <p>{description[1]}</p>
                              <dl>
                                <dt>证据路径</dt>
                                <dd>{finding.instance_path || "文档级检查"}</dd>
                                <dt>契约路径</dt>
                                <dd>{finding.schema_path || "不适用"}</dd>
                                <dt>规则代码</dt>
                                <dd>{finding.code}</dd>
                              </dl>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {report.findings.length === 0 && (
                      <p className="no-findings">
                        <ShieldCheck size={18} aria-hidden="true" />
                        保留这份报告，用于后续对照。
                      </p>
                    )}
                    {report.findings_truncated && (
                      <p>仅显示前 50 项，修复后可重新检查。</p>
                    )}
                  </div>
                  <div className="report-footer">
                    <span>检查器 {report.checker_version}</span>
                    <button onClick={download} className="download">
                      <ArrowDownToLine size={15} aria-hidden="true" />
                      下载报告
                    </button>
                  </div>
                  <details className="fingerprint">
                    <summary>证据指纹</summary>
                    <code>
                      {report.evidence_sha256 ?? "本次未能生成规范化摘要"}
                    </code>
                    <p>用于关联本次输入；字段路径与摘要不保证匿名。</p>
                  </details>
                </div>
              )}
            </section>
          </div>

          <section id="workflow" className="workflow">
            <div className="workflow-title">
              <Workflow size={18} aria-hidden="true" />
              <h2>一次检查，三个环节</h2>
            </div>
            <ol>
              <li>
                <span>1</span>
                <div>
                  <strong>提交证据</strong>
                  <p>工具声明与单次调用记录</p>
                </div>
              </li>
              <li>
                <span>2</span>
                <div>
                  <strong>核对契约</strong>
                  <p>由本地检查器执行验证</p>
                </div>
              </li>
              <li>
                <span>3</span>
                <div>
                  <strong>查看依据</strong>
                  <p>结论、范围与问题定位</p>
                </div>
              </li>
            </ol>
          </section>
          <section id="testing" className="testing">
            <div>
              <FlaskConical size={20} aria-hidden="true" />
              <h2>当前能检查什么？</h2>
            </div>
            <p>
              参数类型、必填字段、结构化结果与调用关联。返回结果缺少契约时会标记“未检查”；证据不足、规则不支持或数值可能失真时会明确拒判。
            </p>
            <details>
              <summary>
                测试方式与当前边界 <ChevronDown size={15} aria-hidden="true" />
              </summary>
              <div className="testing-detail">
                <p>
                  网页通过本机 API 调用与 CLI
                  相同的检查器。验收包含真实浏览器操作、CLI
                  结果对照、数字保真、错误恢复和键盘访问。
                </p>
                <p>
                  当前处理已保存的调用记录。真实 MCP 接入是下一项；Agent
                  诊断、修复及记忆按后续迭代交付。三个内置案例均为合成示例。
                </p>
                <code>
                  <Terminal size={15} aria-hidden="true" />
                  uv run --frozen pytest
                </code>
              </div>
            </details>
          </section>
          <WorkspaceFooter beforeNavigate={beforeNavigate} />
        </div>
      </main>
    </div>
  );
}
