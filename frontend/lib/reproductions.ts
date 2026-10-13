import { z } from "zod";
import { readJSON, RunApiError, runSchema } from "./runs";

export const reproductionScenario = z.enum(["pass", "tool_error", "timeout", "response_lost"]);
export type ReproductionScenario = z.infer<typeof reproductionScenario>;
const uuid = z.string().regex(/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/);
const text = z.string().min(1).max(800);
export const catalogSchema = z.strictObject({
  version: z.literal(1),
  cases: z.array(z.strictObject({ id: reproductionScenario, title: text.max(80), description: text, expected: text })).length(4),
  ready: z.boolean(), reason: z.string().max(128).nullable(), active_run_id: uuid.nullable(),
}).refine(value => new Set(value.cases.map(item => item.id)).size === 4);
export type ReproductionCatalog = z.infer<typeof catalogSchema>;
const acceptedSchema = z.strictObject({ run: runSchema, reused: z.boolean() });
const cancelSchema = z.strictObject({ run_id: uuid, status: z.enum(["cancel_requested", "already_finished"]) });
export const pendingSchema = z.strictObject({ request_id: uuid, scenario: reproductionScenario });
export type PendingReproduction = z.infer<typeof pendingSchema>;
export const PENDING_KEY = "awb-pending-reproduction-v1";

export async function loadCatalog(signal: AbortSignal) {
  const { value } = await readJSON("/api/reproductions/catalog", signal);
  const result = catalogSchema.safeParse(value);
  if (!result.success) throw new RunApiError("场景目录不符合约定，已停止接收新的复现。请更新服务后重查。");
  return result.data;
}
export async function startReproduction(request: PendingReproduction, signal: AbortSignal) {
  const { value } = await readJSON("/api/reproductions", signal, { method: "POST", body: JSON.stringify(pendingSchema.parse(request)) });
  const result = acceptedSchema.safeParse(value);
  if (!result.success || result.data.run.run_id !== request.request_id || result.data.run.scenario !== request.scenario) {
    throw new RunApiError("提交响应关联不符合约定。请只查询本次请求的结果。");
  }
  return result.data;
}
export async function cancelReproduction(id: string, signal: AbortSignal) {
  const { value } = await readJSON(`/api/reproductions/${uuid.parse(id)}/cancel`, signal, { method: "POST", body: "{}" });
  const result = cancelSchema.safeParse(value);
  if (!result.success || result.data.run_id !== id) throw new RunApiError("停止响应不符合约定，请查询真实运行状态。");
  return result.data;
}
export function submissionMessage(error: unknown) {
  if (error instanceof RunApiError) {
    if (error.status === 429) return "已有网页任务占用执行槽。先查看当前运行，结束后再新建。";
    if (error.status === 400 || error.status === 403) return "提交未被接受，请确认本机服务与页面版本一致后重查准备状态。";
    if (error.status === 409) return "请求标识发生冲突，本次未新建运行。请查询已有记录。";
    if (error.status === 410) return "本请求对应的旧记录已清理，服务不会重新执行。";
  }
  return "提交结果待确认。网络中断不代表任务未执行；这里只查询本次请求，不自动重新提交。";
}
export function rejectionIsDefinite(error: unknown) {
  return error instanceof RunApiError && [400, 403, 409, 410, 429].includes(error.status ?? 0);
}
export function scenarioConfig(scenario: ReproductionScenario) {
  return { profile: "isolated-fixture", scenario: reproductionScenario.parse(scenario), seed: 0, lifetime: 45 };
}
export function scenarioCommand(scenario: ReproductionScenario) {
  return `uv run --frozen agent-workbench sandbox-check --server-config ./awb-${reproductionScenario.parse(scenario)}-server.json --case examples/mcp/lookup-case.json`;
}
export function saveDownload(bytes: Uint8Array<ArrayBuffer> | string, name: string) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function readinessMessage(reason: string | null) {
  const messages: Record<string, string> = {
    store_not_initialized: "运行数据库尚未初始化，请在项目根目录运行 uv run --frozen agent-workbench runs init。",
    schema_incompatible: "运行数据库需要升级，请先备份并按文档初始化到当前版本。",
    store_unavailable: "本机运行数据库暂不可用，请检查本机服务后重新检查。",
    locking_unavailable: "本机执行锁不可用，请检查服务状态后重新检查。",
    image_not_prepared: "固定执行镜像尚未准备好，请按文档完成显式准备；网页不会自动构建或下载镜像。",
    docker_unavailable: "Docker 暂不可用，请启动本机 Docker 后重新检查。",
    runner_busy: "已有任务占用网页执行槽。请先查看当前运行；若任务中断，请按文档显式核对。",
  };
  return reason && Object.hasOwn(messages, reason) ? messages[reason] : "本机尚未准备好。请按准备说明检查数据库、Docker 与固定镜像，然后重新检查。";
}
