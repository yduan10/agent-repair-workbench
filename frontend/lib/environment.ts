"use client";
/** UI-08: live readiness of the local service, Docker image, model and execution slots.
 * Read-only GET polling. Pauses while the tab is hidden. */
import { useCallback, useEffect, useRef, useState } from "react";
import { readJSON } from "./runs";
import { loadCatalog, readinessMessage, type ReproductionCatalog } from "./reproductions";
import { loadAnalysisCatalog, type AnalysisRunCatalog } from "./analysis-runs";

export type CheckTone = "pass" | "fail" | "unknown" | "running" | "neutral";
export type EnvironmentCheck = { key: "api" | "runner" | "model" | "analysis"; label: string; tone: CheckTone; summary: string; detail?: string; href?: string };
export type EnvironmentState = {
  loading: boolean;
  checkedAt: number | null;
  api: { ok: boolean; checkerVersion: string | null };
  reproduction: ReproductionCatalog | null;
  analysis: AnalysisRunCatalog | null;
  /** Start time of the last successful read of each catalog; a failed read never advances it. */
  reproductionAt: number | null;
  analysisAt: number | null;
  checks: EnvironmentCheck[];
  overall: CheckTone;
  refresh: () => void;
};

const modelReasons: Record<string, string> = {
  MODEL_NOT_CONFIGURED: "启动本机服务时没有提供模型接口配置。",
  MODEL_CONFIGURATION_INVALID: "模型接口配置无效，请检查环境变量。",
  INPUT_BOUND_UNVERIFIED: "模型输入上限尚未确认，暂不允许发起模型分析。",
};

export function modelReasonMessage(reason: string | null) {
  return reason ? modelReasons[reason] ?? "模型暂不可用。" : "已配置。";
}

/** A single refused read (429 while another reader holds the lock) keeps the last value; repeated failures mean it is stale. */
const STALE_AFTER_FAILURES = 2;
const unreadable = (key: "runner" | "model", label: string, detail: string): EnvironmentCheck => ({ key, label, tone: "unknown", summary: "无法读取", detail });

function summarize(api: EnvironmentState["api"], reproduction: ReproductionCatalog | null, analysis: AnalysisRunCatalog | null, loading: boolean): EnvironmentCheck[] {
  if (loading && !api.ok) return [{ key: "api", label: "本机服务", tone: "neutral", summary: "正在检查…" }];
  if (!api.ok) return [{ key: "api", label: "本机服务", tone: "fail", summary: "未连接", detail: "页面无法访问 127.0.0.1:8030。请在项目根目录启动本机服务后刷新。", href: "/docs/27-local-development-guide#启动网页" }];
  const checks: EnvironmentCheck[] = [{ key: "api", label: "本机服务", tone: "pass", summary: "已连接", detail: api.checkerVersion ? `检查器 ${api.checkerVersion}` : undefined }];
  if (reproduction) {
    const busy = reproduction.active_run_id !== null;
    const runHref = busy ? `/workspace/tasks?run=${reproduction.active_run_id}` : undefined;
    checks.push(reproduction.ready
      ? { key: "runner", label: "复现环境", tone: busy ? "running" : "pass", summary: busy ? "正在运行一项复现" : "Docker 与镜像就绪", href: runHref }
      : reproduction.reason === "runner_busy"
        ? { key: "runner", label: "复现环境", tone: "running", summary: "正在运行一项复现", detail: "结束后可开始新的复现。", href: runHref ?? "/workspace/tasks" }
        : { key: "runner", label: "复现环境", tone: "unknown", summary: "未就绪", detail: readinessMessage(reproduction.reason), href: "/workspace/connections#status" });
  } else checks.push(unreadable("runner", "复现环境", "场景目录读取失败，请检查本机服务版本。"));
  if (analysis) {
    checks.push(analysis.model.configured
      ? { key: "model", label: "模型", tone: "pass", summary: "已配置" }
      : { key: "model", label: "模型", tone: "unknown", summary: "未配置", detail: `${modelReasonMessage(analysis.model.reason)}契约检查仍可使用。`, href: "/workspace/connections#model" });
    const slot = analysis.slot;
    checks.push(slot.status === "available"
      ? { key: "analysis", label: "分析执行槽", tone: "pass", summary: "空闲" }
      : slot.status === "busy"
        ? { key: "analysis", label: "分析执行槽", tone: "running", summary: "正在分析", href: `/workspace/diagnosis?analysis=${slot.task_id}` }
        : { key: "analysis", label: "分析执行槽", tone: "fail", summary: "需要恢复", detail: "上次分析中断，需要在终端运行 analyses reconcile 后再发起新分析。", href: "/docs/27-local-development-guide#运行记录与恢复" });
  } else checks.push(unreadable("model", "模型与分析", "分析目录读取失败，模型配置和分析执行槽状态未知。请检查本机服务版本后重新检查。"));
  return checks;
}

function overallTone(checks: EnvironmentCheck[]): CheckTone {
  if (checks.some(c => c.tone === "fail")) return "fail";
  if (checks.some(c => c.tone === "unknown")) return "unknown";
  if (checks.some(c => c.tone === "running")) return "running";
  if (checks.some(c => c.tone === "neutral")) return "neutral";
  return "pass";
}

const healthSchema = (value: unknown) => {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  return v.status === "ok" ? { checkerVersion: typeof v.checker_version === "string" ? v.checker_version.slice(0, 64) : null } : null;
};

export function useEnvironment(intervalMs = 15000): EnvironmentState {
  const [state, setState] = useState<Omit<EnvironmentState, "refresh" | "checks" | "overall"> & { reproductionFailures: number; analysisFailures: number }>({
    loading: true, checkedAt: null, api: { ok: false, checkerVersion: null }, reproduction: null, analysis: null,
    reproductionAt: null, analysisAt: null, reproductionFailures: 0, analysisFailures: 0,
  });
  const controller = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    let api = { ok: false, checkerVersion: null as string | null };
    try {
      const { value } = await readJSON("/api/health", abort.signal);
      const health = healthSchema(value);
      if (health) api = { ok: true, checkerVersion: health.checkerVersion };
    } catch { /* api stays offline */ }
    if (abort.signal.aborted) return;
    const startedAt = Date.now();
    // A catalog read can be refused briefly (429) while another reader holds the lock;
    // keep the previous value once instead of flashing "无法读取", but never past STALE_AFTER_FAILURES.
    const [reproduction, analysis] = api.ok
      ? await Promise.all([loadCatalog(abort.signal).catch(() => undefined), loadAnalysisCatalog(abort.signal).catch(() => undefined)])
      : [null, null];
    if (abort.signal.aborted) return;
    setState(previous => ({
      loading: false, checkedAt: Date.now(), api,
      reproduction: reproduction === undefined ? previous.reproduction : reproduction,
      analysis: analysis === undefined ? previous.analysis : analysis,
      reproductionAt: reproduction ? startedAt : api.ok ? previous.reproductionAt : null,
      analysisAt: analysis ? startedAt : api.ok ? previous.analysisAt : null,
      reproductionFailures: reproduction === undefined ? previous.reproductionFailures + 1 : 0,
      analysisFailures: analysis === undefined ? previous.analysisFailures + 1 : 0,
    }));
  }, []);
  useEffect(() => {
    let timer: number | undefined;
    const schedule = () => { window.clearInterval(timer); if (!document.hidden) timer = window.setInterval(load, intervalMs); };
    const visibility = () => { if (!document.hidden) load(); schedule(); };
    const external = () => load();
    load();
    schedule();
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("awb-environment-refresh", external);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("awb-environment-refresh", external);
      controller.current?.abort();
    };
  }, [load, intervalMs]);
  const { reproductionFailures, analysisFailures, ...rest } = state;
  // Stale values are withdrawn for every consumer, not only for the summary rows.
  const reproduction = reproductionFailures >= STALE_AFTER_FAILURES ? null : state.reproduction;
  const analysis = analysisFailures >= STALE_AFTER_FAILURES ? null : state.analysis;
  const checks = summarize(state.api, reproduction, analysis, state.loading);
  return { ...rest, reproduction, analysis, checks, overall: overallTone(checks), refresh: load };
}

/** Pages call this after starting or stopping work so the sidebar status updates at once. */
export function requestEnvironmentRefresh() {
  window.dispatchEvent(new Event("awb-environment-refresh"));
}
