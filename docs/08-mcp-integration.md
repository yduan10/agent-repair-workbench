# P0-02：真实 MCP stdio 接入设计与测试计划

版本 0.2 / 2026-10-13。本文为开发规格与已验证实现边界；最终完成状态以台账和评审为准。本阶段只连接受控本地测试 server，先交付 CLI/领域适配；网页接入页已完成交互预览。用户任意工具、写操作、容器资源隔离和故障恢复依赖 P0-03/P0-04。

## 1. 目标与完成定义

对一个明确配置、固定代码版本的本地 MCP server，真实完成握手、工具发现、一次工具调用、标准证据转换、确定性检查，并输出可复核报告。加入至少一个来源明确且固定版本的公开故障复现。仅复制 issue 描述、合成响应或 SDK 单元测试不满足完成门禁。

M1 与 M0 分开：M0 验证用户输入的原始 JSON；M1 首期验证 SDK 解析后的 MCP 应用层值，不声称验证完整原始 wire。二者共享契约验证引擎，但必须在报告中标明不同证据来源和未检查项。

## 2. 选型与版本证据

- 保留 Python 3.12 / uv / Pydantic / jsonschema。
- 已固定 **官方 `mcp==2.3.0`**（mcp-types 同为 2.3.0），先独立安装并验证 Python 3.12 / 既有依赖兼容、真实握手与输出钩子，再通过 `uv add` 生成主项目锁。实际协议为 2025-11-25。wheel SHA 见 fixture README。
- 已核对 `mcp/client/session.py`：`initialize()`、`list_tools(params=...)`、`call_tool(name, arguments, ...)`；结果属性为 snake_case。`call_tool` 会在返回前调用 `validate_tool_result`，需要处理提前抛错导致证据丢失的问题。
- SDK 2.x 同时含较新协议能力。本次采用明确的 legacy initialize 生命周期，首批只接受协商结果 **2025-11-25**，否则返回 unsupported_protocol，不能静默按旧字段解释新协议。新版 discover/扩展结果/多轮输入能力不在本次范围。
- SDK 候选版本进入 implementation 前，先在隔离环境运行最小兼容测试；只有 Python 3.12、既有依赖和指定协议均兼容才通过 `uv add` 固定并生成 lock。兼容失败必须记录 ADR/修改版本，不手改依赖约束绕过。

依据：[官方 SDK](https://github.com/modelcontextprotocol/python-sdk)、[PyPI 精确版本](https://pypi.org/project/mcp/2.3.0/)、[2025-11-25 tools 规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。协议版本选择是受控范围决策，不宣称它是当前最新版。

## 3. 模块边界与执行流程

```text
显式 server 配置 + 单次用例
        ↓ 校验 argv / 工作目录 / 工具名 / 参数
stdio transport + 官方 ClientSession
        ↓ initialize → 核对 protocol_version / capabilities
list_tools 分页 → 冻结目标工具 schema 快照
        ↓ schema 支持检查 → 输入契约预检
call_tool 一次（不自动重试）
        ↓ SDK 应用层响应 + 本地 invocation_id
M1 evidence adapter → 有界确定性 checker
        ↓ 脱敏报告 / 可选本地合成证据导出
```

| 组件 | 职责 | 不允许承担 |
|---|---|---|
| MCP 配置模型 | 审核过的 profile、固定场景枚举；代码内映射 argv/cwd/env | 接受 shell 字符串或网页传来的任意命令 |
| session adapter | 生命周期、分页、冻结声明、单次调用 | 模型决策、自动重试、自动安装 server |
| evidence adapter | 类型/缺失字段/来源转换 | 从文本猜 JSON、修正类型、编造 wire request ID |
| checker adapter | 复用 P0-01 语义、补来源范围 | 将 SDK 异常文本写入公开报告 |
| CLI | `mcp-check --server-config ... --case ...` | 自动保存密钥、把 transport 错误当工具业务失败 |

实际文件：`mcp_config.py`、`mcp_adapter.py`、`mcp_models.py`、`mcp_cli.py`、`tests/fixtures/mcp_server.py`。主测试为 `tests/test_mcp_adapter.py`，公开案例门禁为 `tests/test_mcp_public_case.py`。

## 4. 字段映射与判定规则

| MCP 字段/情况 | 内部处理 | 结论边界 |
|---|---|---|
| Tool.name / inputSchema / outputSchema | 映射 tool.name/input_schema/output_schema，保留声明快照哈希 | 不存在 outputSchema 时 output=not_checked |
| tools/call name / arguments | 原值映射调用输入，不强制类型转换 | 输入预检失败不执行工具 |
| CallToolResult.structuredContent | 用 model_fields_set 区分缺失和显式 null | 不用 `value or {}` 抹掉 null/空对象 |
| content 文本/图片/资源块 | 只记录块类型和受限长度元数据；不拉取链接 | 不把文本块自动解析为 structuredContent |
| isError=true | 工具业务失败；清除不适用的成功断言 | 不能因为 schema 通过就判成功 |
| JSON-RPC error / 断连 / 超时 | adapter outcome 独立字段，固定错误代码 | 超时/断连不能假定未执行，不自动重试 |
| SDK 返回无法支持的类型 | unsupported_result → inconclusive | 不当作普通成功结果 |
| 工具不存在/重复名字/分页循环 | 固定错误，终止本次调用 | 不猜选第一个同名工具 |

### Adapter outcome 与 CLI 退出码

`adapter_outcome` 固定枚举与退出码按下表处理。M1 包装还含 `preflight_findings`（脱敏规则/路径数组），记录未执行情况下的配置/声明/输入问题，不编造执行后的 Report。

| 情况 | adapter_outcome | contract_report | CLI 退出码 |
|---|---|---|---|
| 正常收到SDK CallToolResult且非isError | completed | 真实结果的Report | passed=0、failed=1、inconclusive=2 |
| 配置或输入契约明确无效，尚未调用 | precheck_rejected | null，依据在preflight_findings | 1 |
| schema/协议/结果类型不支持或无法可靠检查 | unsupported | 未调用或无法映射时null，否则inconclusive Report | 2 |
| 收到isError=true | tool_error | 映射成工具失败的Report | 1 |
| 尚未发出call前握手失败/断连 | transport_error | null | 2 |
| call收到明确关联的JSON-RPC error | protocol_error | null，不冒充工具业务结果 | 2 |
| 已发出call后超时/取消/断连，未取得可靠终态 | outcome_unknown | null | 2 |

预检只消费声明支持性和输入验证结果；调用尚未发生时，不能用完整 M0 Report 的 `result_missing` 或整体 status 阻止合法输入。实现应提供明确的 schema/input 预检入口；若复用完整 checker，则只采纳其 schema 与输入范围结果，不把预期缺结果错误发布为本次工具失败。必须补“合法输入无结果仍实际执行一次”和“非法输入执行次数为零”的真实 fixture 计数验收。

### SDK 提前校验与证据保留

本产品需要自己按受支持 schema 子集给出字段路径；SDK 的 `validate_tool_result` 若先抛异常，会丢掉结构化结果并可能在异常中包含原值。

实现选项确定为：使用很薄的 `ClientSession` 子类，仅覆写该输出验证钩子，把输出验证责任转交既有有界 checker；**协议解析、关联、握手仍由 SDK 负责**。工具声明先经过本产品支持范围预检，不支持的 schema 不调用。钩子改变必须有“无效结果仍送达 checker 并判 failed”的真实 stdio 集成测试，防止空覆写形成验证缺口。禁止从 RuntimeError 文本反向抽取原值；SDK 升级时此钩子测试是强制门禁。

### 证据来源与关联 ID

M1 对外报告使用 `mcp_report_version: 1`，嵌入 P0-01 检查报告与 source 元数据。带原值的 M0 envelope 仅在内存传给限时 checker；**不把新字段塞入禁止额外字段的 M0 envelope**：

- `source.kind = mcp_sdk_normalized`、SDK/协议/适配器版本、server 配置摘要、用例摘要、工具声明哈希；公开案例额外含固定源码提交与完整源码树摘要。用例 ID 包含在摘要输入中，不以原值发布。
- 每次调用分配本地 invocation_id，并只在本地 envelope 的调用/结果配对；标注 `association = sdk_dispatch`。SDK 已关联的结果不伪称为原始 wire ID 核验。
- `wire_json_integrity = not_checked`：SDK 可能已处理重复键或浮点数字，不能把重序列化后的文本称为无损原始证据。M0 原始文件保真测试仍保留，M1 报告另列此限制。
- SDK 值中的非有限数/超出支持数值范围按既有拒判规则处理。受控 fixture 先用字符串、布尔、明确整数和简单 object，不借此宣称所有 MCP JSON 已保真。
- M1 报告有独立 `adapter_outcome`、嵌入的 `contract_report`（不存在则 null）及 `source`。成功的应用层契约判断不代表 wire 完整性通过；界面必须展示未检查项。
- 普通报告仅含规则代码、路径、版本、摘要。原始 arguments/results 默认只在内存；合成 fixture 可显式导出，真实敏感证据不自动落盘。

## 5. 执行与资源边界

P0-02 server 限项目内审核过的 Python fixture，以及独立隔离目录中固定版本的公开案例。用户 JSON 只选择固定 profile/scenario，绝对 executable、argv、cwd 由已审核代码映射；`shell=False`；不运行 npx/uvx 在线自动拉取、不从 server instructions 执行命令。

- cwd 固定为受控 fixture 目录；env 显式允许必要运行项，不继承整份用户凭据环境；不开放 sampling、roots 写入、elicitation 或任意远端资源访问。
- 一个 session 一次调用，initialize、完整分页发现、输入预检、call、输出检查各默认最多 5 秒；整个流程从配置校验开始共享 20 秒单调时钟 deadline，每阶段取 min(阶段上限, 剩余预算)，不能把阶段限时简单累加。两个 checker 均为可终止子进程并计入该总预算。退出清理预算另 7 秒；受控 fixture 测试允许少量调度误差但必须记录实测总时长。预算在call前耗尽为unsupported/check_budget_exhausted，call发出后尚无可靠终态则outcome_unknown；已收到结果但验证预算耗尽保留completed + inconclusive。
- 最多 10 页/100 个工具；重复 cursor 和同名声明拒绝；每份规范化证据≤1 MiB，超限 inconclusive。
- stdout/stderr 在 SDK 解码前的硬字节限制和完整进程树隔离属于 P0-03。本阶段仅受控 fixture；应用层大小上限不宣称能抵御恶意 server 的无限输出。
- 正常退出、fixture 异常退出、受控超时需清理直接子进程；“无任意孙进程泄漏”“CPU/内存硬限制”须 P0-03 后再对外承诺。
- 不写数据库、不自动重放、不伪称 exactly-once。仅 call 已发出且无可靠终态的超时/断连记录 outcome_unknown；其余按 outcome 表处理。只读 fixture 也需用户重新发起下一次运行。

### 清理预算与配置决策（ADR-008）

原草案 3 秒不符合 SDK 2.3.0 的 shield 清理流程：writer flush 0.5 秒、grace/terminate/reap 各 2 秒，预算合计约 6.5 秒，因此调整为 7 秒并保留调度余量。独立 CLI SIGTERM 实测清理 4.36 秒，无直接子进程残留。此值属于已审核 fixture 的预算依据，不是对任意外部进程的硬截止承诺；不修改 SDK 私有常量绕过清理。

固定 profile 比可配置 argv 更严格：用户 JSON 不能传 command/args/cwd/env。公开历史 profile 先以固定脚本 `--verify-only` 核验完整源码树，再启动 server；验证不下载、不安装、不自动修复文件，失败即拒判。源码树与本地环境仍以可信单用户开发工作区为前提，完整抗并发替换和沙箱能力属于 P0-03。

## 6. 公开案例

来源：[python-sdk #3644](https://github.com/modelcontextprotocol/python-sdk/issues/3644)。问题描述：返回 Pydantic 模型的 serialization_alias / computed_field 与生成的 outputSchema 不一致。

报告者所用提交固定为 `2118f14f8a19bc158d8a1cf90af58d85d187f849`（通过官方 GitHub commit API 展开短 SHA）。**这是受影响候选提交，不是修复提交**。该 issue 的关闭状态不作为复现证据。本轮独立探针已经实际复现；产品 CLI 与完整源码校验的最终门禁见 [公开案例记录](experiments/P0-02-public-case.md) 和代码评审。

步骤：

1. 在隔离目录固定候选 server 源码 SHA、Python/Pydantic/全部依赖 lock，运行最小返回模型；保持本项目客户端环境隔离。
2. 在真实 stdio server 中注册返回对象的工具，实际 list/call；保存可分享的合成输入、声明、返回值和哈希。
3. 验证输出字段 `userId` / `doubled` 与声明是否矛盾，并由本产品 checker 指明路径。不得只运行 issue 中的 func_metadata 片段冒充 MCP 集成。
4. 若该历史 SDK 无法协商指定协议、无法安装、现象不成立或 schema 不在支持范围，记录具体阻塞；不得改结果、悄悄弱化 schema 或换成合成案例计完成。
5. 固定版本复现通过才计公开案例；修复版本对照作为后续修复阶段补充，不把本轮设计写成实际成果。

## 7. 测试矩阵与强制门禁

| ID | 层/输入 | 必须验证的结果 |
|---|---|---|
| M1-U01 | 字段映射 | input/output schema，missing/null/空对象准确映射 |
| M1-U02 | 纯文本/多媒体/资源内容 | 不猜 JSON、不联网取资源，检查范围正确 |
| M1-U03 | isError/协议错误/SDK异常 | 三者区分，无原值与异常文本泄漏 |
| M1-U04 | 不支持 schema/协议/非有限数 | inconclusive 或预检拒绝，不假成功 |
| M1-U06 | 预检与总deadline | 合法输入不会因result_missing被阻止；非法输入不执行；两次checker均计入20秒 |
| M1-U05 | 配置 | shell字符串、非受控路径、未允许env拒绝，不执行命令 |
| M1-I01 | 真实 stdio 成功 server | 真实 handshake/list/call；输出契约通过；版本可核对 |
| M1-I02 | 真实错误结果 server | SDK钩子保留结果，checker定位失败；不能验证被绕过 |
| M1-I03 | 输出缺失/未声明输出/文本块 | missing、not_checked、工具失败语义按声明区分 |
| M1-I04 | 分页/同名/cursor循环 | 有界遍历、拒绝歧义、不无限等待 |
| M1-I05 | 受控崩溃/超时 | 固定 adapter outcome，无自动重试，直接子进程退出 |
| M1-I06 | 日志含敏感标记 | stdout报告、公开诊断不含参数/结果/环境密钥 |
| M1-R01 | 公开案例固定提交 | 真实 stdio 复现，证据及环境可复跑；未成功则不完成 |
| M1-R02 | M0 全部回归 | 原始JSON数字/重复键/BOM保真不受M1修改影响 |
| M1-R03 | 来源与关联 | M1明确normalized/not_checked，不能冒充wire ID/字节保真 |
| M1-Q01 | 独立代码评审 | 适配、版本、边界审查；P0/P1全部修复并复审 |

命令：`uv run --frozen pytest -m "not public_case"` 为确定性 CI；公开案例先按实验 README 显式准备独立依赖环境，再执行 `AWB_PUBLIC_CASE=1 uv run --frozen pytest -m public_case`。默认公开案例跳过，不能把跳过算通过；本项完成须单独实跑。真实模型不参与本项，不消耗 DeepSeek token。

## 8. 开发顺序与变更门禁

1. 固定 SDK 与 fixture 的兼容实验及 lock；测试握手版本与输出验证钩子。
2. 先实现 M1 包装/报告的明确来源边界，并对 M0 接口做回归。
3. 实现受控 stdio、分页、预检、单次调用、CLI。
4. 运行公开案例，不成功就保持该验收未完成。
5. 独立 review → 修复 → 复审 → 台账更新；随后进入 P0-03 的执行隔离设计。

网页“工具接入”在任意用户命令安全边界就绪前仍显示预览；可以先接入只读的已审核 fixture 演示，但必须单独测试，不能因页面已画好就开放任意执行。
