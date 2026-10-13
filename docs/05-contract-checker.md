# P0-01：离线工具调用契约检查器

版本：`evidence schema_version=1`，`report schema_version=1`。

## 1. 边界

输入是从工具声明和调用观察整理的本地 JSON envelope，不是直接声称支持全部 MCP wire format。适配官方 SDK 在 P0-02 实现。首版一次检查一个工具的一次调用；不分析完整 Agent trace、不执行工具、不诊断根因、不生成补丁。

CLI：`agent-workbench check PATH [--timeout SECONDS]`。默认 5 秒，范围 0.1～30 秒，耗时从 worker 启动前计算；超时终止并回收 worker。stdout 输出单个 JSON 报告，stderr 只输出无数据值的错误代码。报告不写文件，重定向由用户控制。

## 2. 输入 envelope

```json
{
  "schema_version": 1,
  "tool": {
    "name": "lookup",
    "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"], "additionalProperties": false},
    "output_schema": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
  },
  "call": {"call_id": "c1", "tool_name": "lookup", "arguments": {"id": 1}},
  "result": {"call_id": "c1", "is_error": false, "structured_content": {"count": 2}}
}
```

- 所有 envelope 对象禁止未知字段，类型不做隐式转换。name/call_id 非空且最多 128 字符；arguments 必须是对象。
- input_schema 必填且顶层 type=object；output_schema 可省略，提供时必须顶层 type=object，显式 null 不接受。
- result 可省略，显式 null 不接受；结构化结果字段可省略，JSON null 视为真实返回值，按 schema 检查。
- 版本必须是 JSON 整数 1，不接受 true 或字符串 "1"。
- 不接受重复 JSON key、NaN、Infinity、非 UTF-8、超过 1 MiB、超过 32 层或 20000 个节点的数据。CLI 仅接受常规文件，拒绝目录/FIFO/符号链接，避免阻塞或隐式读取其他目标。
- 数字支持边界：JSON 整数按 Python 整数处理（受解析器数字长度上限限制）；小数/指数须能以有限浮点数的最短十进制表示精确往返，且整数值浮点数须在二进制表示中精确等于原数。下溢、上溢、精度丢失（如 `1e-999`、`1e999`、`9007199254740993.0`、`1e23`）返回 `unsupported_number`、inconclusive，不四舍五入后校验。`multipleOf` 按支持数值的十进制有理数精确计算，禁止用 epsilon 放宽。

## 3. schema 支持范围

仅 Draft 2020-12；省略 `$schema` 默认此版本，显式版本必须为 `https://json-schema.org/draft/2020-12/schema`。

支持：`$schema`、`title`、`description`、`$comment`、`default`、`examples`、`type`、`properties`、`required`、`additionalProperties`、`items`、`prefixItems`、`minItems`、`maxItems`、`uniqueItems`、`minProperties`、`maxProperties`、`minLength`、`maxLength`、`minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`、`multipleOf`、`enum`、`const`、`allOf`、`anyOf`、`oneOf`、`not`。子 schema 可为布尔值。

任何未列关键字（包括 `$ref`、`$dynamicRef`、`$id`、`format`、`pattern`、`patternProperties`、`unevaluatedProperties`、`contains`、自定义关键字）返回 unsupported_schema，不能静默跳过后声称完整验证。只遍历 schema 位置，不能将 properties 中的字段名或 const/default/examples 数据误识别为关键字。

schema meta-validation 使用 jsonschema；标识为 unsupported 与语法 malformed 区分。未知关键字属于不支持，不推断其语义。超过深度/节点或计算限额必须 inconclusive。限制范围通过 ADR-005 维护，扩展要新增正负测试。

## 4. 结果语义

| status | 意义 | 退出码 |
|---|---|---|
| passed | 已声明且支持的适用检查通过 | 0 |
| failed | 有确定的调用/结果契约失败 | 1 |
| inconclusive | 证据缺失/无效、不支持或检查执行未完成 | 2 |

CLI 语法错误也退出 2，stderr 仅输出 `invalid_arguments`，不回显用户参数；`--help` 输出用法说明。正常 `check` 请求的失败以报告表示。超时、资源异常、worker 非正常退出均不得返回 0。

检查顺序：输入 envelope → 两个 schema 的适用性/有效性 → 工具名匹配 → 参数检查 → result 存在性 → call_id 关联 → is_error → 输出检查。schema 不支持或格式无效时停止检查并 inconclusive，不产生其他确定结论。其他情况：确定失败优先于结果缺失；缺失结果且无确定失败时 inconclusive。

错误工具结果仍是 failed（该次工具调用失败），但不能单凭 is_error 推断工具有实现 bug。工具返回错误时输出检查 skipped；call_id 不匹配时该结果不能归属当前调用，输出检查 skipped。无 output_schema 时输出检查 not_checked；即使总 status=passed，报告也不声称输出验证通过。有 output_schema 且返回成功时，缺失 structured_content 是 failed。

## 5. 报告

包含：schema_version、checker_version、evidence_sha256、status、checks、findings。输入无法解析则 evidence_sha256=null；已解析且满足资源限制的 JSON 采用排序 key、紧凑分隔、UTF-8、禁止非有限数的规范化表示计算 SHA-256。它不是 RFC 8785、不是签名；算法固定在 report v1。

`unsupported_number` 无法在规定的数字表示下生成保真规范化摘要，故 evidence_sha256=null；这不表示原 JSON 语法无效。

checks 至少包含 input/output 的 passed/failed/not_checked/skipped。每条 finding 包含 code、phase、instance_path（envelope 的 JSON Pointer）、schema_path（相对对应 schema 的 JSON Pointer）。Pointer 按 RFC 6901 转义 `~` 和 `/`。不包含错误原文、schema 常量值、调用参数值、工具名或 call_id 原值。

错误代码：invalid_document、input_limit_exceeded、unsupported_number、unsupported_schema、invalid_schema、tool_name_mismatch、input_schema_violation、result_missing、result_call_mismatch、tool_error、structured_content_missing、output_schema_violation、check_timeout、checker_error、input_unreadable。

findings 最多 50 条；通过 `findings_truncated` 告知裁剪，发现任何失败后裁剪不能变成 passed。按固定验证遍历顺序输出；同一输入/相同锁定依赖报告一致。成功不产生 findings。

## 6. 必须验证的反例

参数整数变字符串；必填缺失；额外字段；嵌套数组元素错误；含 `/~` 的 key；非法 schema；远端/本地 ref；未知关键字；properties 的字段恰好名为 `$ref`；const 中含 `$ref`；error 结果；缺结果；关联错误；output schema 缺失；结构化内容缺失/null；版本 true；重复 key；Unicode；极深输入；超大文件；非正常 worker；计时超限；错误信息中的敏感值不进入报告。

两个内置样本标记为 synthetic；仅证明检查行为，不属于公开历史 bug 复现。公开案例接入及真实 MCP 结果另在 P0-02 验证。
