import type { RunView, SandboxReport } from "./runs";
import { reproductionScenario } from "./reproductions";

export type ReproductionTone = "pass" | "fail" | "unknown" | "neutral";
export type ReproductionResult = { title: string; detail: string; tone: ReproductionTone };

/** Said once on the page: what an unknown outcome means for the user. */
export const OUTCOME_UNKNOWN_DETAIL = "发送后没有收到结果，无法确认工具是否执行；不会自动重试。";

/** Describes observed evidence; never changes the stored execution verdict. */
export function reproductionResult(run: RunView, report: SandboxReport): ReproductionResult {
  const contract = report.mcp.contract_report;
  const matching = report.execution.scenario === run.scenario
    && report.mcp.source.config_sha256 === run.config_sha256
    && report.mcp.source.case_sha256 === run.case_sha256;
  if (!matching) return { title: "报告与运行不匹配", detail: "报告中的场景或配置与这条运行不同，无法判断是否复现。请重新运行该场景。", tone: "unknown" };
  // Only the four web scenarios have an expectation the page knows. Terminal-only scenarios (wrong_type, oom, …)
  // may fail or exhaust resources on purpose, so the page states what happened without judging it.
  if (!reproductionScenario.safeParse(run.scenario).success) {
    if (run.status === "outcome_unknown") return { title: "结果未知", detail: OUTCOME_UNKNOWN_DETAIL, tone: "unknown" };
    if (run.status === "cancelled") return { title: "已停止", detail: "运行在完成前被停止。已经发给工具的调用可能仍然执行过。", tone: "neutral" };
    if (report.execution.cleanup === "unconfirmed") return { title: "未确认清理", detail: "运行结束后没有确认容器已清理，请按下方信息检查。", tone: "fail" };
    return run.status === "succeeded"
      ? { title: "调用成功", detail: "这个场景从终端发起，网页不判断结果是否符合场景预期；请查看下方的检查结果。", tone: "neutral" }
      : { title: "调用失败", detail: "这个场景从终端发起，网页不判断失败是否就是该场景要复现的结果；请查看下方的检查结果和错误。", tone: "neutral" };
  }
  if (report.execution.error || report.execution.oom_killed || report.execution.cleanup === "unconfirmed") {
    return { title: "运行环境出错", detail: "容器报错、内存超限或未确认清理。处理下方错误后重新运行。", tone: "fail" };
  }
  if (run.status === "failed" && run.scenario === "tool_error"
    && report.execution.cleanup === "removed" && report.mcp.adapter_outcome === "tool_error"
    && contract?.checks.input === "passed" && contract.status === "failed"
    && contract.findings.some(f => f.code === "tool_error" && f.instance_path === "/result")) {
    return { title: "已复现工具错误", detail: "参数检查通过，工具在 /result 返回错误，判定为不通过；容器已清理。", tone: "neutral" };
  }
  if (run.status === "succeeded" && run.scenario === "pass" && report.execution.cleanup === "removed"
    && report.mcp.adapter_outcome === "completed" && contract?.status === "passed"
    && contract.checks.input === "passed" && contract.checks.output === "passed") {
    return { title: "正常调用通过", detail: "参数和返回结果都符合契约；容器已清理。", tone: "pass" };
  }
  if (run.status === "outcome_unknown") return { title: "结果未知", detail: OUTCOME_UNKNOWN_DETAIL, tone: "unknown" };
  if (run.status === "cancelled") return { title: "已停止", detail: "运行在完成前被停止。已经发给工具的调用可能仍然执行过。", tone: "neutral" };
  return { title: "与预期不符", detail: "结果和所选场景的预期不同，请查看下方的不符合项。", tone: "fail" };
}

/** Plain-language status before (or without) a verified report. */
export function statusSentence(run: RunView): ReproductionResult {
  switch (run.status) {
    case "queued": return { title: "排队中", detail: "等待容器启动。离开页面不会停止运行。", tone: "neutral" };
    case "running": return { title: "运行中", detail: "工具调用正在容器中运行，每 2 秒刷新一次。离开页面不会停止运行。", tone: "neutral" };
    case "outcome_unknown": return { title: "结果未知", detail: OUTCOME_UNKNOWN_DETAIL, tone: "unknown" };
    case "cancelled": return { title: "已停止", detail: "运行在完成前被停止。已经发给工具的调用可能仍然执行过。", tone: "neutral" };
    case "succeeded": return { title: "调用成功", detail: "运行已结束，但这条运行没有可核验的报告。", tone: "neutral" };
    case "failed": return { title: "调用失败", detail: "运行已结束，但这条运行没有可核验的报告。", tone: "fail" };
  }
}
