# 企业代码质量审计报告：P0-02 阶段复审 / DOC-02

- **审计对象**：公开案例 prepare/server/probe 与实验依赖；受控 fixture；MCP 取消、内容摘要/大小、公开 profile 接入增量；DOC-02 角色目录约定。
- **审计版本**：2026-10-13 独立审查副本；23 个文件（锁文件另按来源与版本审查）。文件摘要见 `P0-02-review-snapshot.json`，该文件 SHA-256：`096e39ae66fb8d40e25dde38e7982a8a1ca64018f47d6e723f7ed72620f94411`。
- **审查目录**：`<review-workspaces>/code-review`。源码未修改；报告由独立 reviewer `/root/code_review_m0` 编写，主 Agent 负责合入。
- **技术栈**：Python 3.12、AnyIO、官方 MCP SDK 2.3.0、Pydantic、jsonschema、uv。
- **业务场景 / 严苛度**：General SaaS / Mission-Critical。
- **审计状态**：最终增量复审。公开完整集合校验与真实产品 CLI 验收均通过，原 P1 已关闭。

## 1. 代码质量评估卡

- **综合得分**：100 / 100（本次范围未遗留确认缺陷；不代表零风险）。
- **门禁**：本批 P0-02 本地能力与 DOC-02 范围 Pass；M1-CR-01 已修复且独立复审关闭。生产部署整体仍为 Conditional Pass / 未评估，不签发上线许可。主 Agent 应结合另一名核心 reviewer 和全量回归决定里程碑完成。
- **本批范围之外**：远端 CI；任意不可信 server 的资源隔离（后续 P0-03）；新 UI（另批）。依赖漏洞零项来自主实现者，未在本批重复漏洞扫描。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 unresolved (M1-CR-01 fixed and independently verified)
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped local capability Pass; overall production Conditional Pass / not assessed
NOT ASSESSED: remote CI, P0-03 isolation, UI-02; outside this review scope
```

### 独立执行证据

独立审查目录运行：

```sh
uv run --frozen pytest -q tests/test_mcp_adapter.py
uv run --frozen ruff check src/agent_workbench/mcp_adapter.py src/agent_workbench/mcp_config.py src/agent_workbench/mcp_models.py src/agent_workbench/mcp_cli.py tests/test_mcp_adapter.py
```

原样输出：

```text
.........................................                                [100%]
All checks passed!
```

共 41 项 MCP 测试通过。另核对 `agent_workbench.__file__` 指向本独立目录，未调用主项目源码。

在目录隔离要求提出前，曾按当时授权在主目录执行固定公开实验，输出：

```text
public_case_environment_verified
{"reproduced": true, "case": "modelcontextprotocol/python-sdk#3644"}
```

此次公开实验确实完成官方原始 SDK stdio 握手、发现、调用；输出 `userId/doubled` 与声明 `user_id` 不一致。不是合成 fixture 冒充历史故障。该初次证据仅证明独立公开 probe；最终产品公开 profile 证据见后文。


### 最终复审证据与 P1 关闭依据

- 修复位置：`prepare.py:70–123`，完整实际文件与目录集合逐项核对，并拒绝 symlink、额外源码、字节码及缓存目录；`--verify-only` 路径只读，无下载、安装或产物写入。
- 命令 `uv run --frozen python -I -B experiments/public_mcp_case/test_prepare.py` 输出：

```text
...............
----------------------------------------------------------------------
Ran 15 tests in 0.680s

OK
```

- 命令 `AWB_PUBLIC_CASE=1 uv run --frozen pytest -m public_case` 输出：

```text
.                                                                        [100%]
1 passed, 140 deselected in 3.09s
```

该用例真实启动产品 CLI，再启动固定历史 SDK server；断言 exit 1、adapter completed、contract failed、输出 `/required` 违规及 source revision/协议/未检查 wire 信息。

- 独立新增两次真实 CLI 反例：仅在 reviewer 的临时 artifact 树分别增加 `.py` 和 symlink 目录，结束后移除自身新增条目。两次均在启动 server 前拒绝：

```json
{"scenario":"extra_module","exit":2,"code":"public_source_unverified","protocol_version":null}
{"scenario":"symlink_directory","exit":2,"code":"public_source_unverified","protocol_version":null}
```

- 恢复后 `--verify-only` 再次通过：1717 文件，树 SHA-256 `02876b5641d24d36561ac4d6f7ab341bb014fbc2d8f9912dff79893d1dae33aa`；所有实验 Ruff 检查输出 `All checks passed!`。
- M1-CR-01 关闭；可信本机工作区中的并发恶意文件替换仍明确不在本实验保证内。

## 2. 生产事故风险推演（已关闭缺陷的原始场景）

> **场景：复现目录额外模块覆盖锁定依赖**
> **触发条件**：复用的公开源码目录多出一个 `src/pydantic.py`。
> **机制**：prepare 只逐项核对 archive 原有文件；server/probe 将源码 src 放入 sys.path 首位，因此额外模块可能抢先导入。
> **可见症状**：仍报告 `source_modified:false` 与环境已验证，但执行内容不再等于固定源码加锁定依赖。
> **影响范围**：该本地公开案例运行及其复现结论。
> **可检测性**：现有逐文件摘要校验不能发现额外文件；必须补完整目录集合校验。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### M1-CR-01：源码校验不拒绝新增可导入文件（已修复、独立复审关闭）

- **原缺陷位置**：修复前 `experiments/public_mcp_case/prepare.py:65–73`；导入入口为 `server.py` / `probe.py` 的 sys.path prepend。
- **维度**：12 依赖与供应链治理；6 安全与数据合规。
- **置信度**：[confirmed]。
- **复现**：临时独立副本复制已验证 archive，调用实际 prepare；在解包源码添加 `src/pydantic.py`，再次调用实际 prepare。未修改主项目实现或正式 source tree。
- **实际输出**：

```json
{"extra_importable_module_exists":true,"source_modified":false,"source_files_verified":1717}
```

- **问题**：报告承诺源码未修改，却未验证完整文件集合；新增 `.py` 或可加载字节码可能影响执行。
- **最小修复方向**：将实际文件/目录集合与 archive 期望集合比较；拒绝多余条目、软链接及异常文件类型，然后逐文件核对摘要。对已有 pycache 明确拒绝或安全清理；`-B` 仅禁止写缓存，不能单独证明不会读既有缓存。prepare `--verify-only` 必须离线且不安装。
- **验证方式**：干净目录通过；额外 `.py`、`.pyc`、软链接目录、缺失/修改文件均拒绝；随后用主客户端 public profile 完成真实 stdio 并由 checker 判输出 schema 失败。

### P2 — 主要缺陷

none。docs/08 已同步 7 秒 SDK 清理预算、固定 profile、应用层报告版本与实际测试命令。

### P3 — 次要缺陷

none。

### 已核对无新增缺陷的增量

- `mcp_adapter.py` 在预检后、`sent=True` 前显式 cancellation checkpoint；真实集成测试验证预检期间取消不会进入 call handler。
- 每个 session 最多一次调用；错误输入、分页循环、同名工具均不调用。wrong_type 经过覆写 SDK hook 后由 checker 判 failed，未因钩子覆写跳过校验。
- 完整规范化 CallToolResult 在生成摘要前计入大小预算，包括正文；超限保留已收到结果事实，报告 inconclusive。
- JSON 文本不被猜为 structuredContent；资源链接仅记录类型与计数，不进入报告原值。该测试与静态路径支持受控 fixture 边界，不证明任意插件网络隔离。
- 公开 profile 派生固定 argv；静态检查显示 verify-only 非零/不合法报告会闭锁，且核对 commit、archive、lock。实际集成现已通过；污染源码反例也由真实 CLI 拒绝。
- DOC-02 及角色 README 明确只有目录/接口约定，不宣称 P0-05 已实现；诊断只读、修复受隔离门禁、验证不能修改程序结果，公共 MCP/模型/预算组件不复制进角色。新增角色测试需进入 pytest discovery。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | MCP/确定性检查/未来模型角色分离 |
| 2 | SOLID 与现代设计 | 0 | 本批为有界适配器与目录约定 |
| 3 | 并发、异步与资源安全 | 0 | 真实取消、超时、直接子进程回收测试；任意进程树隔离未评估 |
| 4 | 容错与防御性编程 | 0 | 取消与响应未知、协议错误、工具错误区分 |
| 5 | 性能、伸缩性与计算效率 | 0 | 单次调用、页/工具/应用层大小限制；不评吞吐 |
| 6 | 安全与数据合规 | 见 M1-CR-01 | 环境覆盖/报告无原值；不重复计分 |
| 7 | 可观测性与运维友好度 | 0 | 来源与未检查项明确，报告为 SDK normalized |
| 8 | 类型安全与契约表达 | 0 | 严格配置、固定 outcome、明确 missing/null |
| 9 | 可测试性与死代码 | 0 | 41 项真实 stdio 测试，fixture 明示合成 |
| 10 | 工程规范与一致性 | 0 | Ruff 通过；DOC-02 不偷报实现完成 |
| 11 | 数据与事务完整性 | 0 | 无数据库写入，不宣称 exactly-once |
| 12 | 依赖与供应链治理 | 1 | M1-CR-01；固定 archive/commit/隔离 lock 的正确意图未覆盖额外文件 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| M1-CR-01 | Defect P1 | `/root/docs_review` 实施，`/root` 合入 | 2026-10-13 | fixed / independently verified |

## 6. 架构防腐与长效治理建议

1. 给完整来源校验加离线反例测试：额外文件、缓存、链接、内容变更与缺失，避免复现报告夸大可复跑性；成本为一组临时目录测试。
2. SDK 升级保留 wrong_type、missing/null、取消与子进程回收真实 stdio 门禁；这些行为依赖 SDK，不以静态 mock 替代。
3. 角色实现开始时同时更新测试发现路径与能力状态，避免新增目录被误认为多 Agent 已运行；不预建无人使用的注册框架。

## 7. 审计声明

本报告仅覆盖摘要清单对应快照。后续改动需增量复审；完整产品、多 Agent、模型、自动修复、生产部署均不在本阶段通过声明中。无风险豁免。M1-CR-01 为实测确认，不是猜测。公开 profile 端到端验收已完成。本地受控能力通过不等于生产环境或任意 MCP server 安全通过。
