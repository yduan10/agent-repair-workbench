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
  if (!result.success) throw new RunApiError("无法读取场景列表（不符合约定），暂时不能开始复现。通常是页面与服务版本不一致：请重启本机服务后刷新。");
  return result.data;
}
export async function startReproduction(request: PendingReproduction, signal: AbortSignal) {
  const { value } = await readJSON("/api/reproductions", signal, { method: "POST", body: JSON.stringify(pendingSchema.parse(request)) });
  const result = acceptedSchema.safeParse(value);
  if (!result.success || result.data.run.run_id !== request.request_id || result.data.run.scenario !== request.scenario) {
    throw new RunApiError("服务的回应与本次提交对不上，无法确认是否已开始。请点「查询提交结果」，不要重新提交。");
  }
  return result.data;
}
export async function cancelReproduction(id: string, signal: AbortSignal) {
  const { value } = await readJSON(`/api/reproductions/${uuid.parse(id)}/cancel`, signal, { method: "POST", body: "{}" });
  const result = cancelSchema.safeParse(value);
  if (!result.success || result.data.run_id !== id) throw new RunApiError("无法确认是否已停止。请刷新查看运行状态。");
  return result.data;
}
export function submissionMessage(error: unknown) {
  if (error instanceof RunApiError) {
    if (error.status === 429) return "已有一个复现在运行，同一时间只能运行一个。等它结束后再开始。";
    if (error.status === 400 || error.status === 403) return `服务拒绝了这次提交（HTTP ${error.status}），通常是版本不一致。请重启本机服务后刷新页面。`;
    if (error.status === 409) return "这次提交与已有运行冲突，没有新建运行。请在下方运行记录中查看。";
    if (error.status === 410) return "这次提交对应的记录已被清理。如需再次运行，请重新开始复现。";
  }
  return "连接中断，无法确认复现是否已开始。请点「查询提交结果」，不要重复提交。";
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
    store_not_initialized: "运行数据库尚未初始化。请在项目根目录运行 uv run --frozen agent-workbench runs init，然后重新检查环境。",
    schema_incompatible: "运行数据库版本过旧。请先备份，再运行 uv run --frozen agent-workbench runs init 升级。",
    store_unavailable: "无法打开运行数据库。请查看本机服务终端的错误输出。",
    locking_unavailable: "无法获取运行锁，可能有另一个服务进程在使用同一个数据库。关闭多余的进程后重新检查环境。",
    image_not_prepared: "缺少复现用的 Docker 镜像。请先在项目根目录运行 uv run --frozen python containers/p0_03/prepare.py。",
    docker_unavailable: "Docker 未运行。启动 Docker 后重新检查环境。",
    runner_busy: "已有一个复现在运行，同一时间只能运行一个。等它结束后再开始。",
  };
  return reason && Object.hasOwn(messages, reason) ? messages[reason] : "本机还不能运行复现。请确认数据库、Docker 和镜像都已就绪，然后重新检查环境。";
}
