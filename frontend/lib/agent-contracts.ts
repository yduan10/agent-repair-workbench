import { z } from "zod";
export const roleIds = ["diagnosis", "repair", "verification"] as const;
export const toolIds = ["read_evidence", "read_contract", "read_source", "check_contract", "request_reproduction"] as const;
const jsonSchema = z.record(z.string(), z.unknown());
const catalogSchema = z.strictObject({
  catalog_version: z.literal(3), cli_runtime_available: z.literal(true), web_runtime_available: z.literal(true),
  roles: z.array(z.strictObject({ id: z.enum(roleIds), allowed_tools: z.array(z.enum(toolIds)).max(5), output_schema: jsonSchema })).length(3),
  tools: z.array(z.strictObject({ name: z.enum(toolIds), request_schema: jsonSchema })).length(5),
  task_schema: jsonSchema, state_schema: jsonSchema, summary_schema: jsonSchema,
}).refine(data => new Set(data.roles.map(role => role.id)).size === 3
  && new Set(data.tools.map(tool => tool.name)).size === 5
  && data.roles.every(role => new Set(role.allowed_tools).size === role.allowed_tools.length));
export type AgentCatalog = z.infer<typeof catalogSchema>;
export type AgentRole = typeof roleIds[number];

export async function loadAgentContracts(signal: AbortSignal): Promise<AgentCatalog> {
  const response = await fetch("/api/agent-contracts", { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) });
  if (!response.ok || !response.body) throw new Error("catalog_unavailable");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > 131072) { await reader.cancel(); throw new Error("catalog_limit"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return catalogSchema.parse(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)));
}

/** User-facing labels for the catalog. Wording only; the catalog itself comes from the API. */
export const roleLabels: Record<AgentRole, { label: string; duty: string; boundary: string }> = {
  diagnosis: { label: "诊断", duty: "从调用证据定位问题；证据不足时保留假设。", boundary: "可申请检查和复现，不能修改代码。" },
  repair: { label: "修复", duty: "针对已定位的问题，在限定的文件范围内提出修复建议。", boundary: "只输出建议，不应用补丁，不能修改验收规则。" },
  verification: { label: "验证", duty: "核对证据与修复建议，列出仍需验证的部分。", boundary: "可申请检查和复现，不能自行判定候选通过。" },
};
export type AgentTool = typeof toolIds[number];
export const toolLabels: Record<AgentTool, { label: string; purpose: string }> = {
  read_evidence: { label: "读取调用证据", purpose: "读取指定任务的摘要、检查项与事件。" },
  read_contract: { label: "读取工具契约", purpose: "读取固定版本的输入与输出契约。" },
  read_source: { label: "读取源码片段", purpose: "读取授权快照中的文件，单次最多 200 行。" },
  check_contract: { label: "申请契约检查", purpose: "用检查器重新检查原始调用证据。" },
  request_reproduction: { label: "申请复现", purpose: "运行审核过的内置场景，只接受固定配置。" },
};
