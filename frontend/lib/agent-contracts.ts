import { z } from "zod";
export const roleIds = ["diagnosis", "repair", "verification"] as const;
export const toolIds = ["read_evidence", "read_contract", "read_source", "check_contract", "request_reproduction"] as const;
const jsonSchema = z.record(z.string(), z.unknown());
const catalogSchema = z.strictObject({
  catalog_version: z.literal(2), cli_runtime_available: z.literal(true), web_runtime_available: z.literal(false),
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
