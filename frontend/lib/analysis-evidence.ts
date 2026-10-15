import { z } from "zod";
import { readJSON, RunApiError } from "./runs";
import { AnalysisDetail } from "./analyses";
const uuid = z.string().regex(/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const check = z.enum(["passed", "failed", "not_checked", "skipped"]);
const itemSchema = z.strictObject({
  ref: z.strictObject({ evidence_id: uuid, sha256: hash }),
  kind: z.enum(["report", "source", "contract", "unavailable"]),
  title: z.string().min(1).max(120), description: z.string().min(1).max(800),
  findings: z.array(z.strictObject({ code: z.string().max(128), path: z.string().max(8192) })).max(50),
  report: z.strictObject({ status: z.enum(["passed", "failed", "inconclusive"]), input: check, output: check }).nullable(),
  source: z.strictObject({ path: z.literal("source/server.py"), start_line: z.literal(107), end_line: z.literal(110), text: z.string().max(16384) }).nullable(),
  schemas: z.strictObject({ tool_name: z.literal("lookup"), input_schema: z.record(z.string(), z.unknown()), output_schema: z.record(z.string(), z.unknown()).nullable() }).nullable(),
}).refine(v => (v.kind === "report") === (v.report !== null) && (v.kind === "source") === (v.source !== null) && (v.kind === "contract") === (v.schemas !== null) && (v.kind === "report" || v.findings.length === 0));
const responseSchema = z.strictObject({ schema_version: z.literal(1), task_id: uuid, summary_sha256: hash, evidence: z.array(itemSchema).max(32) });
export type ReadableEvidence = z.infer<typeof itemSchema>;
export async function loadEvidence(detail: AnalysisDetail, signal: AbortSignal) {
  const { value } = await readJSON(`/api/analyses/${uuid.parse(detail.summary.task_id)}/evidence`, signal);
  const result = responseSchema.safeParse(value);
  if (!result.success || result.data.task_id !== detail.summary.task_id || result.data.summary_sha256 !== detail.sha256
      || result.data.evidence.length !== detail.summary.evidence_refs.length
      || !result.data.evidence.every((v, i) => v.ref.evidence_id === detail.summary.evidence_refs[i].evidence_id && v.ref.sha256 === detail.summary.evidence_refs[i].sha256)) throw new RunApiError("证据与当前分析版本不一致，未展示。请刷新后查看。");
  return result.data.evidence;
}
