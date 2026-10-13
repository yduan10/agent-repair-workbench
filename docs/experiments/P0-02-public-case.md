# P0-02：公开历史问题 #3644 的真实 stdio 复现实验

日期：2026-10-13。实施者：`/root/docs_review`，本轮已转为实验实施角色，**不作为本实验的独立代码评审者**。状态：独立探针已复现，等待主产品 MCP 适配器复验及独立代码评审。

## 1. 结论与范围

已在官方 Python SDK 固定提交上，通过真实 stdio 的 `initialize → tools/list → tools/call` 复现公开问题：声明要求 `user_id`，实际结构化输出只有 `userId` 与 `doubled`。独立 JSON Schema 验证命中 `required` 失败；现有 P0-01 检查器读取该次 SDK 规范化证据，同样报告 `output_schema_violation`。

这是**公开历史缺陷的最小复现，使用公开合成输入**。它不是人工改坏工具的故障注入，也不是真实用户生产数据。未调用模型、未修改上游 SDK、未通过 metadata 片段替代真实协议调用。该结果不说明主产品 MCP 适配器已经完成，也不证明上游当前版本是否已修复。

## 2. 官方来源与固定版本

- [官方 issue #3644](https://github.com/modelcontextprotocol/python-sdk/issues/3644)：报告者指出 v2 提交 `2118f14` 的 `serialization_alias` / `computed_field` 问题。官方 API 返回该 issue 已关闭且 `state_reason=duplicate`；关闭状态不作为修复依据。
- [完整提交](https://github.com/modelcontextprotocol/python-sdk/commit/2118f14f8a19bc158d8a1cf90af58d85d187f849)：`2118f14f8a19bc158d8a1cf90af58d85d187f849`，经官方 Git commits API 核实。提交说明为文档更新，不是修复提交。
- [官方源码归档](https://codeload.github.com/modelcontextprotocol/python-sdk/tar.gz/2118f14f8a19bc158d8a1cf90af58d85d187f849)：4,225,626 字节，SHA-256 `c860806fd728927747fdc0b9624b824d545e48e4199e1be9cc94906f6e44aba9`。
- [上游相关源码](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/src/mcp/server/mcpserver/utilities/func_metadata.py)：`model_post_init` 生成默认 validation schema；`convert_result` 使用 `model_dump(mode="json", by_alias=True)` 序列化。

首次下载曾因超时取得不完整归档，该文件没有用于安装或运行。重新完成下载、验证完整归档后才执行实验。`prepare.py` 固定归档摘要，并核对完整文件及目录集合、1,717 个普通文件的大小与内容摘要；额外文件、额外目录、缺失条目和所有符号链接均拒绝，复用已下载源码时也重新核验。

## 3. 环境与依赖锁

实验独立位于 `experiments/public_mcp_case/`，Python **3.12.13**；使用该目录的 `pyproject.toml`、`uv.lock` 和 `.venv`。没有修改主项目的 `src`、`pyproject.toml` 或 `uv.lock`。

该历史提交为含 `mcp` 与 `mcp-types` 的 monorepo，并依赖动态 Git 版本构建。实验直接从固定归档的 `src` 与 `src/mcp-types` 加载两个原始包，避免为了构建而改写上游版本或包元数据。**没有使用新版 SDK wheel 冒充历史源码。** 探针启动时校验两个包的 `__file__` 均在指定历史源码目录下。

第三方运行依赖来自该提交的 runtime requirements；全部解析结果与下载摘要固定在实验 `uv.lock`。没有安装上游开发、文档构建和示例组；运行也不执行上游构建钩子。源代码许可证为 MIT。

| 项目 | 本次值 |
|---|---|
| 实验依赖 lock SHA-256 | `9bb751c83ef7964e3b64a5a9551e113ea40dc499a4d6127e56a190e0fbb55be8` |
| 已安装第三方依赖数 | 26 |
| Pydantic / pydantic-core | 2.14.1 / 2.50.1 |
| jsonschema | 4.26.0 |
| anyio | 4.15.1 |
| 协商协议 | 2025-11-25 |

所有已安装包及版本同时保存在运行产物 `reproduction.json`。这是本次环境的精确复现，不宣称重建了 issue 作者当时未公布的完整依赖环境。

## 4. 最小运行代码审阅与权限

`server.py` 只注册 issue 的 `Out` 模型和返回 `Out(user_id=3)` 的 `tool`。没有手写输出 schema，没有删除必填字段，没有覆盖 SDK 的服务端转换逻辑。只启动 stdio，不监听网络端口、不执行 shell、不访问其他项目文件、不写业务数据。

已只读查看上游直接路径：MCPServer 初始化/stdio 启动、工具注册及调用、`FuncMetadata` schema 生成和返回值转换、客户端 initialize/list/call 与 stdio 生命周期。发现 schema 生成和序列化使用不同模式的路径与观察结果一致。该审阅**不是整个上游仓库或全部传递依赖的安全认证**。

探针使用同提交 SDK `ClientSession`，仅覆写客户端 `validate_tool_result` 钩子，以保留服务端已经返回的不合法结构化结果；随后使用独立 `Draft202012Validator` 检查。该钩子没有修改 server，且探针断言它确实被调用。协议握手、发送和结果关联仍由官方 SDK 完成。

运行命令使用清空的环境启动探针，只提供 PATH 和禁止 bytecode 的标记；未传入模型密钥或用户凭据。原始 stderr 与证据仅位于忽略的实验产物目录。本例数据均来自公开最小模型，因此允许显式导出。20 秒请求 deadline 之外，SDK 有独立有界清理；这不等于 P0-03 的容器或通用不可信进程隔离。

## 5. 运行与结果

从项目根目录运行：

```sh
python3 -I -B experiments/public_mcp_case/prepare.py
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  experiments/public_mcp_case/.venv/bin/python -I -B experiments/public_mcp_case/probe.py
```

实际探针输出：

```json
{"reproduced": true, "case": "modelcontextprotocol/python-sdk#3644"}
```

探针退出 **0** 表示历史失败已被预期地复现，**不表示工具契约通过**。如果导入路径、协议、声明或返回值不符合断言，则不能报复现成功；运行失败会覆写失败产物并移除旧 envelope，避免把上一轮成功误认为本轮结果。

真实 `tools/list` 返回的 outputSchema：

```json
{"properties":{"user_id":{"title":"User Id","type":"integer"}},"required":["user_id"],"type":"object","title":"Out"}
```

真实 `tools/call` 返回 `isError=false`，其 structuredContent：

```json
{"userId":3,"doubled":6}
```

独立验证器定位 `schema_path=["required"]`、实例根路径。具体违反的是必填字段 `user_id` 缺失；本 schema 未禁止额外字段，不能把 `doubled` 的存在本身称为另一项违反。

再将该次真实调用的规范化 envelope 交给现有检查器：

```sh
.venv/bin/python -m agent_workbench check \
  artifacts/public-mcp-case/synthetic-public-case-envelope.json \
  > artifacts/public-mcp-case/contract-report.json
```

实际退出 **1**，报告 `status=failed`、`input=passed`、`output=failed`，finding 为：

```json
{"code":"output_schema_violation","phase":"output","instance_path":"/result/structured_content","schema_path":"/required"}
```

这一步验证了 P0-01 引擎能够检查 SDK 规范化证据；真实 P0-02 产品入口与资源边界仍需主实现复验。

## 6. 证据清单与主适配器接入

产物均位于 `artifacts/public-mcp-case/`，不提交原始运行文件：

| 文件 | 内容 |
|---|---|
| `issue-3644.json` / `commit.json` | 官方 API 来源 |
| `python-sdk.tar.gz` / `python-sdk-2118f14…/` | 摘要固定的历史源码 |
| `source-verification.json` | 归档和依赖锁摘要、完整源码文件核验数 |
| `synthetic-public-case-envelope.json` | 本次真实 stdio 调用的 SDK 规范化合成证据 |
| `reproduction.json` | 协议、环境版本、源码和证据摘要、实际耗时、断言结果 |
| `contract-report.json` | 本产品 P0-01 对证据的确定性失败报告 |
| `server-stderr.log` | 本次为空；保留实验诊断位置 |

Envelope 文件字节 SHA-256：`480f9625261b2bce432f51145ebc1cbf9ca59189964b6268ac9bdf32f62be8f5`。P0-01 报告内规范化证据 SHA-256：`1b30aefd61d144e077597cfeba665904b89f48d19f295d1f73595a595b6e30d7`。两者算法输入不同，摘要不同属于预期。

主适配器可使用：

```text
executable: <project-root>/experiments/public_mcp_case/.venv/bin/python
argv: ["-I", "-B", "<project-root>/experiments/public_mcp_case/server.py"]
cwd: <project-root>/experiments/public_mcp_case
tool: tool
arguments: {}
```

这些是本机路径，迁移到其他机器后按仓库位置重新生成。Envelope 的调用 ID 是探针的本地关联标记，来源为 `real_stdio_sdk_normalized`；`wire_json_integrity=not_checked`，不宣称对原始 wire 数字或重复 key 做过保真验证。

## 7. 复验门禁

独立代码 reviewer 需复查准备脚本、受控 server 和探针，并运行冻结安装及真实 stdio 复验。主产品 MCP 适配器必须对同一个 server 得到 `completed + contract_report.failed`、指出相同字段路径，不能仅引用本探针输出计产品适配完成。本次尚未验证修复版本、自动补丁、模型诊断、写工具、恶意 server、任意进程树或跨平台能力。

## 8. 独立评审 P1 修复与只读启动核验

独立 reviewer 找到原准备脚本的漏洞：它检查归档内已有文件，却不拒绝额外文件，因此 `src/pydantic.py` 等文件可能覆盖已经锁定的第三方依赖。此问题不能由旧的 `source_modified:false` manifest 掩盖。

本次修复在独立工作副本 `<review-workspaces>/public-case` 实施，交根任务整合；不由本实施者自行判定 code review 通过。

- `verify_source()` 是纯只读函数，重新读取固定归档及实际源码树；核对完整文件、目录集合和每个文件的内容，不依赖上次生成的 manifest。
- 禁止额外 `.py`、无源 `.pyc`、`__pycache__`、空目录和目录/文件符号链接。没有“忽略所有 cache”的例外。
- probe 与历史 server 使用 `-I -B` 启动，隔离隐式导入路径并禁止新 bytecode。旧产物若含 cache，核验拒绝；明确移走该实验源码目录后，由准备命令从固定归档重新构造，不自动删除用户目录。
- `--verify-only` 不下载、不启动 uv、不安装、不更新 manifest 或其他文件。主适配器应在 5 秒上限内调用 `python -I -B prepare.py --verify-only`，成功后才运行历史 server。
- 成功退出 0，stdout 为单 JSON，字段如下；失败退出 2，只返回固定错误 `code`，不含路径、文件内容和异常原文。

```json
{"code":"source_verified","commit":"2118f14f8a19bc158d8a1cf90af58d85d187f849","archive_sha256":"c860806fd728927747fdc0b9624b824d545e48e4199e1be9cc94906f6e44aba9","lock_sha256":"9bb751c83ef7964e3b64a5a9551e113ea40dc499a4d6127e56a190e0fbb55be8","source_tree_sha256":"02876b5641d24d36561ac4d6f7ab341bb014fbc2d8f9912dff79893d1dae33aa","source_files_verified":1717,"source_modified":false}
```

`source_tree_sha256` 算法：文件相对上游源码根目录的 POSIX 路径与内容 SHA-256 组成二元数组，按路径排序，以 `ensure_ascii=False`、紧凑分隔符的 JSON 编码为 UTF-8 后计算 SHA-256。目录集合单独完整核验，目录 mtime、权限不进入摘要。该检查针对本地可信实验的当前快照，不承诺阻止核验后恶意并发改文件。

`test_prepare.py` 提供可重复反例：额外 `.py`、无源 `.pyc`、cache、额外/缺失目录、缺失文件、相同长度内容篡改、文件/目录/根目录 symlink、损坏归档、失败信息脱敏，以及 verify-only 不调用下载/安装/写盘路径。真实官方树的子进程核验还检查 5 秒超时与运行前后文件集合/mtime/size 均不变。

执行：`.venv/bin/python -I -B experiments/public_mcp_case/test_prepare.py`。修复首轮 15 项测试通过，实际官方树只读核验约 0.6 秒；后续正式复审以独立 reviewer 结果为准。


## 产品 CLI 复验（2026-10-13）

主项目 `agent-workbench mcp-check --server-config examples/mcp/public-server.json --case examples/mcp/public-case.json` 已通过真实 SDK 2.3.0 客户端连接固定历史源码 server：预期退出 1，adapter_outcome=completed，input=passed、output=failed，规则 output_schema_violation，路径 `/result/structured_content` / `/required`。实际报告含固定提交及完整源码树摘要，不保存返回值；忽略产物 `artifacts/public-mcp-case/product-report.json`。此次耗时 1079ms（单次本机观测，不作性能承诺）。

源码验证在每次公共 profile 启动前以 `--verify-only` 执行并计入总预算。全部 1717 个文件匹配固定归档，源码树摘要 `02876b5641d24d36561ac4d6f7ab341bb014fbc2d8f9912dff79893d1dae33aa`。实验依赖公告扫描 26 项、0 已知漏洞；历史 SDK 源码不在该公告扫描范围。独立代码复审门禁另见 reviews。
