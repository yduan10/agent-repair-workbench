import { z } from "zod";

const checkStatus = z.enum(["passed", "failed", "not_checked", "skipped"]);
export const reportSchema = z.object({
  schema_version: z.literal(1),
  checker_version: z.string(),
  evidence_sha256: z.string().nullable(),
  status: z.enum(["passed", "failed", "inconclusive"]),
  checks: z.object({ input: checkStatus, output: checkStatus }),
  findings: z
    .array(
      z.object({
        code: z.string(),
        phase: z.string(),
        instance_path: z.string(),
        schema_path: z.string(),
      }),
    )
    .max(50),
  findings_truncated: z.boolean(),
});
export type Report = z.infer<typeof reportSchema>;
export type Finding = Report["findings"][number];

export const statusLabels = {
  passed: "通过",
  failed: "不通过",
  inconclusive: "无法判定",
} as const;
export const statusTones = { passed: "pass", failed: "fail", inconclusive: "unknown" } as const;

/** Raw per-phase check status (used by the analysis evidence reader). */
export const checkLabels = {
  passed: "通过",
  failed: "不通过",
  not_checked: "未检查",
  skipped: "已跳过",
} as const;

export type ScopeStatus = "passed" | "failed" | "not_checked";
export const scopeLabels: Record<ScopeStatus, string> = {
  passed: "通过",
  failed: "不通过",
  not_checked: "未检查",
};
export const scopeTones = { passed: "pass", failed: "fail", not_checked: "neutral" } as const;

/** [title, what to do]. */
export const findingLabels: Record<string, [string, string]> = {
  output_schema_violation: [
    "返回结果不符合契约",
    "对照字段路径和契约规则，检查返回值的类型、必填字段或取值范围。",
  ],
  input_schema_violation: [
    "调用参数不符合契约",
    "对照字段路径和契约规则，检查这次调用传入的参数。",
  ],
  invalid_document: [
    "证据格式无效",
    "请检查 JSON 语法、重复键、schema_version 和必填字段。格式参照内置示例。",
  ],
  unsupported_number: [
    "数字可能丢失精度",
    "有数字可能已丢失精度（例如超过 2^53 的整数），因此无法判定。请从原始数据重新导出证据。",
  ],
  result_missing: [
    "缺少返回结果",
    "证据缺少 result，只检查了参数。补充后可以检查返回结果。",
  ],
  unsupported_schema: [
    "契约含暂不支持的规则",
    "检查器支持 JSON Schema 2020-12 的常用子集，不支持 $ref、pattern、format 等规则；顶层契约必须是 object 类型。",
  ],
  invalid_schema: [
    "契约本身无效",
    "input_schema 或 output_schema 不是有效的 JSON Schema，请检查规则写法。",
  ],
  tool_error: [
    "工具返回了错误",
    "工具在这次调用中返回了错误（is_error 为 true），返回结果未按契约检查。请查看工具日志找出原因。",
  ],
  result_call_mismatch: [
    "结果与调用不对应",
    "result.call_id 与 call.call_id 不一致。确认它们来自同一次调用后再检查。",
  ],
  tool_name_mismatch: [
    "工具名称不一致",
    "call.tool_name 与 tool.name 不一致。确认调用的是声明的这个工具。",
  ],
  structured_content_missing: [
    "缺少结构化结果",
    "工具声明了 output_schema，但 result 里没有 structured_content。",
  ],
  input_limit_exceeded: [
    "证据超过检查上限",
    "上限为 1 MiB、32 层嵌套和 20000 个节点。请只保留一次调用的证据。",
  ],
  check_timeout: [
    "检查超时",
    "检查没有在时间上限内完成。请简化契约或证据后重试。",
  ],
  checker_error: [
    "检查器意外退出",
    "检查器进程意外退出。请重试；反复出现时，请查看本机服务终端的错误输出。",
  ],
};
export const unknownFinding: [string, string] = [
  "未知规则代码",
  "页面无法识别这个规则代码。请更新前端，或按代码查阅文档。",
];

/** Plain-language name of the JSON Schema keyword that failed (last segment of schema_path). */
export const keywordLabels: Record<string, string> = {
  type: "类型不符",
  required: "缺少必填字段",
  additionalProperties: "含有契约未声明的字段",
  properties: "字段不符合契约",
  enum: "取值不在 enum 列出的范围内",
  const: "取值与 const 不一致",
  minimum: "数值小于 minimum",
  maximum: "数值大于 maximum",
  exclusiveMinimum: "数值应大于 exclusiveMinimum",
  exclusiveMaximum: "数值应小于 exclusiveMaximum",
  multipleOf: "数值不是 multipleOf 的整数倍",
  minLength: "字符串短于 minLength",
  maxLength: "字符串长于 maxLength",
  minItems: "数组元素少于 minItems",
  maxItems: "数组元素多于 maxItems",
  uniqueItems: "数组有重复元素",
  minProperties: "字段数少于 minProperties",
  maxProperties: "字段数多于 maxProperties",
  items: "数组元素不符合 items",
  prefixItems: "数组元素不符合 prefixItems",
  allOf: "没有满足 allOf 的全部条件",
  anyOf: "没有满足 anyOf 中的任何一项",
  oneOf: "没有恰好满足 oneOf 中的一项",
  not: "满足了 not 排除的条件",
};

const outputSkipReasons: Record<string, string> = {
  result_missing: "缺少 result",
  result_call_mismatch: "结果与调用不对应",
  tool_error: "工具返回了错误",
};

export type ScopeRow = { key: "input" | "output" | "link"; label: string; target: string; status: ScopeStatus; note?: string };

/** What the checker covered: input, output and call/result association.
 * Association is derived from the findings; it is never shown as passed unless
 * both the tool name and call_id comparison actually ran. */
export function checkScope(report: Report): ScopeRow[] {
  const codes = new Set(report.findings.map(finding => finding.code));
  const ran = report.checks.input !== "not_checked";
  const blocked = ran ? undefined : `未执行：${(findingLabels[report.findings[0]?.code ?? ""] ?? unknownFinding)[0]}`;
  const normalise = (status: Report["checks"]["input"]): ScopeStatus => status === "passed" || status === "failed" ? status : "not_checked";

  let outputNote = blocked;
  if (ran && report.checks.output === "skipped") {
    const reason = Object.keys(outputSkipReasons).find(code => codes.has(code));
    outputNote = reason ? outputSkipReasons[reason] : "未执行";
  } else if (ran && report.checks.output === "not_checked") outputNote = "工具没有声明 output_schema";

  let link: ScopeStatus;
  let linkNote: string | undefined;
  if (codes.has("tool_name_mismatch") || codes.has("result_call_mismatch")) {
    link = "failed";
    linkNote = [codes.has("tool_name_mismatch") && "工具名称不一致", codes.has("result_call_mismatch") && "call_id 不一致"].filter(Boolean).join("，");
  } else if (!ran) {
    link = "not_checked";
    linkNote = blocked;
  } else if (codes.has("result_missing")) {
    link = "not_checked";
    linkNote = "缺少 result，无法比对 call_id";
  } else if (report.findings_truncated && report.checks.output === "skipped" && !codes.has("tool_error")) {
    link = "not_checked";
    linkNote = "不符合项过多，结果未完整列出";
  } else link = "passed";

  return [
    { key: "input", label: "调用参数", target: "input_schema", status: normalise(report.checks.input), note: blocked },
    { key: "output", label: "返回结果", target: "output_schema", status: normalise(report.checks.output), note: report.checks.output === "passed" || report.checks.output === "failed" ? undefined : outputNote },
    { key: "link", label: "调用关联", target: "tool_name · call_id", status: link, note: linkNote },
  ];
}

export function verdictSummary(report: Report) {
  if (report.status === "passed") return "已执行的检查全部通过。";
  if (report.status === "failed") {
    const count = report.findings.length;
    return report.findings_truncated ? `发现超过 ${count} 个不符合项，下方列出前 ${count} 个。` : `发现 ${count} 个不符合项，详见下方。`;
  }
  return "信息不足或包含不支持的规则，无法判定。原因见下方。";
}

export const apiErrors: Record<string, string> = {
  checker_busy: "检查器一次只处理一个请求，当前正忙。几秒后重试。",
  checker_unavailable: "检查器没有返回结果。请重试；反复出现时，请查看本机服务终端的错误输出。",
  input_limit_exceeded: "证据超过 1 MiB。请只保留一次调用的证据后重试。",
  origin_forbidden: "本机服务只接受来自 http://127.0.0.1:3010 的请求。请用这个地址打开页面。",
  host_forbidden: "本机服务只接受来自 http://127.0.0.1:3010 的请求。请用这个地址打开页面。",
  request_timeout: "证据上传超时。请重试。",
  request_unreadable: "本机服务没能读取上传的证据。请重试。",
  unsupported_media_type: "页面与本机服务版本不一致。请重启本机服务后刷新页面。",
};
