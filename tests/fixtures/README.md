# P0-02 受控 MCP fixture

`mcp_server.py` 是本项目自己编写的 **synthetic fixture**，不是公开历史故障复现。
使用官方 `mcp==2.3.0` 低层 `Server`、stdio transport 和真实 JSON-RPC；不运行任意命令、
不访问网络、不读取用户文件、不写持久状态。正常工具仅在进程内计数。

## 固定接口

由项目审核 profile 指定 Python 绝对路径、脚本绝对路径和 cwd；启动参数为
`["-I", "-B", "<absolute mcp_server.py>", "--scenario", "<enum>"]`。
不接受命令、文件路径、凭据或用户自定义环境变量；非法参数只输出固定错误代码。

- 工具 `lookup`；输入 `{"id": 1}`。`id` 必须是整数，禁止多余参数。
- 正常输出 `{"count": 1}`；相同会话再次调用时 count 递增。
- 每次进入 call handler 向 stderr 写一行固定 `fixture_call`，可在测试中计数。
  它不包含参数、结果或环境值；生产 CLI 应将 stderr 导向 DEVNULL。
- server identity 为 `awb-contract-fixture` / `1.0.0`。
- 官方客户端 `ClientSession.initialize()` 实际协商 `2025-11-25`。

| `--scenario` | 行为 | 应验证的结果 |
|---|---|---|
| `pass` | 正常结构化结果 | 实际调用并通过 |
| `oversized_content` | 文本块超过 1 MiB，结构化值有效 | 整份结果超限拒判 |
| `resource_content` | 仅返回固定 resource_link，无输出 schema | 只记类型、不拉取 URL，output=not_checked |
| `wrong_type` | count 为固定合成字符串 | 输入通过、输出类型失败 |
| `missing_content` | 仅返回固定文本块 | structuredContent 缺失，不猜测文本 JSON |
| `null_content` | 显式 structuredContent:null | 区分显式 null 与字段缺失 |
| `no_output_schema` | 不声明输出 schema | 输出 not_checked |
| `tool_error` | isError:true | 工具失败，与协议错误区分 |
| `protocol_error` | JSON-RPC -32602 | 协议失败，不伪装业务结果 |
| `paginated` | 第一页 page_one，第二页 lookup | 完整分页发现后才能调用 lookup |
| `cursor_loop` | 重复 cursor=loop、空工具列表 | 拒绝循环，零次调用 |
| `duplicate_tools` | 同一页两个 lookup 声明 | 拒绝歧义，零次调用 |
| `timeout` | call handler 等待 60 秒 | 客户端先超时、不重试；清理进程 |
| `crash` | call handler 内 exit(17) | 调用结果未知，不重试 |
| `unsupported_schema` | output schema 含 $ref | 预检拒判、零次调用，不解析引用 |
| `invalid_schema` | required 含重复字段 | schema 无效、零次调用 |
| `unexpected_protocol` | 握手响应版本改成 2024-11-05 | SDK可解析但超出本产品协议范围，零次调用 |

## 显式 wire 故障注入

SDK 2.3.0 的 server runner 使用 `exclude_none=True`，普通
`CallToolResult(structured_content=None)` 会在出站时变成字段缺失。因此 `null_content`
在官方 server 后的有界内存流里，只给工具响应加上 `structuredContent: null`。
`unexpected_protocol` 同样仅改握手响应中的版本。其余帧照常交给 SDK stdio writer。
这两项是明确的合成协议边界注入，不代表官方 server 自然产生这些响应，也不计公开问题统计。

## 输出验证钩子

官方 `ClientSession.call_tool` 默认先做输出校验。`wrong_type` 会让标准 session 抛
`RuntimeError`，异常文本可能含原值，不能用于公开诊断。应用适配器仅覆写异步
`validate_tool_result(name, result)` 钩子，将收到的结果交给本项目有界 checker；
握手、JSON-RPC 关联、解析保留 SDK 行为。集成验收必须证明 wrong_type 最终由 checker
判 failed，不能把覆写钩子等同验证成功。

字段名为 snake_case，例如 `result.structured_content`，使用
`"structured_content" in result.model_fields_set` 判断是否存在。
分页调用 `session.list_tools(params=types.PaginatedRequestParams(cursor=...))`。
`MCPError.code` 可作内部分类辅助；不要输出其 message 或 data。

## 兼容实验记录

2026-10-13 在独立 Python 3.12.13 环境，以下固定版本共同安装成功：
`mcp==2.3.0`、`mcp-types==2.3.0`、`pydantic==2.14.1`、`jsonschema==4.26.0`、
`fastapi==0.143.0`、`uvicorn==0.54.0`。真 stdio 测得协议 `2025-11-25`、工具发现与调用成功；
标准 session 拒绝错误类型，覆写钩子后可保留错误值；missing/null fields_set 可区别。

本地忽略产物：`artifacts/mcp-spike/probe.py`、`results.json`、`requirements.lock`、
`pypi-mcp-2.3.0.json`。这些兼容探针不替代项目正式集成测试和独立评审。
wheel 的 SHA-256 已对独立读取的 PyPI 精确版本元数据核对：
`dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377`。

官方 stdio 参数 env 会与默认继承的 HOME/LOGNAME/PATH/SHELL/TERM/USER 合并，
不是全量替换。应用层须按审核 profile 显式覆盖这些项；不能修改宿主环境以影响并行任务。
SDK 清理使用 AnyIO shield，等待关闭和进程回收具有自身时间预算；不要私改 SDK 常量。
本 fixture 不创建孙进程，不证明任意外部代码的进程树隔离能力。
