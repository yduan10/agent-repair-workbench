/** UI-08: turn a checker finding into plain language and a source location,
 * using the evidence text the report was produced from. Best effort: when a
 * pointer cannot be resolved the finding is still shown, just not linkable. */
import { findingLabels, keywordLabels, unknownFinding, type Finding } from "../../lib/report";
import { jsonTypeOf, lineColumn, resolvePointer, type JsonAnalysis, type JsonNode } from "./json-tools";

export type FindingView = {
  title: string;
  hint: string;
  /** Plain-language rule, e.g. "类型不符：应为 integer，实际为 string". */
  rule: string | null;
  target: { from: number; to: number; line: number } | null;
};

/** Point a few document-level findings at the exact field they are about. */
const preciseTargets: Record<string, string> = {
  tool_name_mismatch: "/call/tool_name",
  result_call_mismatch: "/result/call_id",
  tool_error: "/result/is_error",
};
const schemaRoots: Record<string, string> = { input: "/tool/input_schema", output: "/tool/output_schema" };
const SHORT = 40;

function lastSegment(pointer: string) {
  const parts = pointer.split("/").slice(1).map(part => part.replace(/~1/g, "/").replace(/~0/g, "~"));
  for (let i = parts.length - 1; i >= 0; i -= 1) if (!/^\d+$/.test(parts[i])) return parts[i];
  return null;
}

function raw(text: string, node: JsonNode | undefined) {
  if (!node) return null;
  const value = text.slice(node.from, node.to);
  return value.length <= SHORT && !value.includes("\n") ? value : null;
}

function stringList(text: string, node: JsonNode | undefined) {
  if (!node || node.kind !== "array") return null;
  const values = node.items!.filter(item => item.kind === "string").map(item => JSON.parse(text.slice(item.from, item.to)) as string);
  return values;
}

function list(values: string[]) {
  const shown = values.slice(0, 4).join("、");
  return values.length > 4 ? `${shown} 等 ${values.length} 个` : shown;
}

function ruleFor(finding: Finding, text: string, analysis: JsonAnalysis): string | null {
  const keyword = lastSegment(finding.schema_path);
  if (!keyword || !finding.code.endsWith("_schema_violation")) return null;
  const label = keywordLabels[keyword] ?? `不满足契约规则 ${keyword}`;
  const root = schemaRoots[finding.phase];
  const rule = root ? resolvePointer(analysis.root, root + finding.schema_path) : null;
  const instance = resolvePointer(analysis.root, finding.instance_path);
  const ruleNode = rule?.exact ? rule.node : undefined;
  const value = instance?.exact ? instance.node : undefined;

  if (keyword === "type" && ruleNode) {
    const expected = ruleNode.kind === "string" ? JSON.parse(text.slice(ruleNode.from, ruleNode.to)) as string : (stringList(text, ruleNode) ?? []).join(" | ");
    return value ? `${label}：应为 ${expected}，实际为 ${jsonTypeOf(text, value)}` : `${label}：应为 ${expected}`;
  }
  if (keyword === "required" && ruleNode && value?.kind === "object") {
    const present = new Set(value.members!.map(member => member.key));
    const missing = (stringList(text, ruleNode) ?? []).filter(name => !present.has(name));
    if (missing.length) return `${label}：${list(missing)}`;
  }
  if (keyword === "additionalProperties" && ruleNode?.kind === "boolean" && value?.kind === "object" && root) {
    const parent = resolvePointer(analysis.root, root + finding.schema_path.replace(/\/additionalProperties$/, ""));
    const declared = parent?.exact ? parent.node.members?.find(member => member.key === "properties")?.value : undefined;
    const known = new Set(declared?.members?.map(member => member.key) ?? []);
    const extra = value.members!.map(member => member.key).filter(name => !known.has(name));
    if (extra.length) return `${label}：${list(extra)}`;
  }
  const expected = raw(text, ruleNode);
  return expected && ruleNode?.kind !== "object" && ruleNode?.kind !== "array" ? `${label}（契约：${keyword} = ${expected}）` : label;
}

export function describeFinding(finding: Finding, text: string | null, analysis: JsonAnalysis | null): FindingView {
  const [title, hint] = findingLabels[finding.code] ?? unknownFinding;
  if (text === null || !analysis) return { title, hint, rule: null, target: null };
  let target: FindingView["target"] = null;
  if (finding.code === "invalid_document" && analysis.issues.length) {
    const issue = analysis.issues[0];
    target = { from: issue.from, to: Math.max(issue.to, issue.from), line: lineColumn(text, issue.from).line };
  } else if (finding.instance_path) {
    const precise = preciseTargets[finding.code] ? resolvePointer(analysis.root, preciseTargets[finding.code]) : null;
    const found = precise?.exact ? precise : resolvePointer(analysis.root, finding.instance_path);
    // A missing member (e.g. /result) falls back to its parent only when that parent is not the whole document.
    if (found && (found.exact || found.depth > 0)) target = { from: found.from, to: found.to, line: lineColumn(text, found.from).line };
  }
  return { title, hint, rule: ruleFor(finding, text, analysis), target };
}
