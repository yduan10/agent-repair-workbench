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
export const statusLabels = {
  passed: "检查通过",
  failed: "发现不符合项",
  inconclusive: "暂时无法判定",
};
export const checkLabels = {
  passed: "通过",
  failed: "不符合",
  not_checked: "未检查",
  skipped: "已跳过",
};
export const findingLabels: Record<string, [string, string]> = {
  output_schema_violation: [
    "返回结果不符合声明",
    "对照结果路径与契约路径，检查字段类型、必填项或取值限制。",
  ],
  input_schema_violation: [
    "调用参数不符合声明",
    "对照参数路径与契约路径，检查本次传入的参数。",
  ],
  invalid_document: [
    "证据格式无效",
    "检查 JSON 语法、重复键、版本和必填字段。请使用完整的证据格式。",
  ],
  unsupported_number: [
    "数值无法保真检查",
    "存在可能丢失精度的数值。本次保留拒判，请核对原始数字和接口约定。",
  ],
  result_missing: [
    "缺少调用结果",
    "补充本次调用的 result，才能继续检查返回结果。",
  ],
  unsupported_schema: [
    "契约含暂不支持的规则",
    "当前支持 JSON Schema 2020-12 的限定子集；引用、正则和 format 等规则暂不检查。",
  ],
  invalid_schema: [
    "契约声明无效",
    "检查 input_schema 或 output_schema 的规则格式。",
  ],
  tool_error: [
    "工具记录了执行错误",
    "这次调用返回了错误状态。需结合真实执行记录继续定位原因。",
  ],
  result_call_mismatch: [
    "结果与调用未关联",
    "确认 call_id 属于同一次调用，再提交检查。",
  ],
  tool_name_mismatch: [
    "工具名称不匹配",
    "核对工具声明和调用记录中的工具名称。",
  ],
  structured_content_missing: [
    "缺少结构化结果",
    "该工具声明了输出契约，请提供对应的 structured_content。",
  ],
  input_limit_exceeded: [
    "证据超过检查限制",
    "限制为 1 MiB、32 层和 20000 个节点，请提交单次调用证据。",
  ],
  check_timeout: [
    "检查超时",
    "检查在时间上限内未完成，请简化单次证据或契约后重试。",
  ],
  checker_error: [
    "检查未完成",
    "检查进程异常结束，请重新检查；持续出现时查看本地运行状态。",
  ],
};
export const apiErrors: Record<string, string> = {
  checker_busy: "检查器正在处理另一个请求，请稍后重试。",
  input_limit_exceeded: "文件超过 1 MiB，请提交较小的单次调用证据。",
  origin_forbidden: "请从 http://127.0.0.1:3010 打开本地工作台。",
  request_timeout: "证据传输超时，请重新提交。",
};
