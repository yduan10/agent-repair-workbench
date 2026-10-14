# 企业代码质量审计报告：P0-05b B3 协作运行时

- **审计对象**：`orchestration/{runtime,budget,role,cli}.py`，三个角色的 `agent.py` 与 `prompts/v1.txt`，配套运行时测试。
- **审计版本**：工作树冻结快照，逐文件 SHA-256 见 `P0-05b-runtime-source-sha256.json`。
- **技术栈**：Python 3.12、LangGraph、asyncio/AnyIO、Pydantic、SQLite 持久摘要。
- **业务场景**：General SaaS（本地单用户、单前台 owner；不是多租户生产服务）。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14。
- **独立性**：评审者未实现本批 B3 源码。本评审不对评审者自己实现的 B2 工具作独立背书；B2 由主线程另行评审。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，未发现本范围内待修缺陷；分数不代表真实模型诊断效果。
- **上线评估结论**：**Pass：本批协作运行时可以集成**。父 P0-05 状态及真实模型 A14 门禁另行判断。
- **审计范围**：10 个生产文件，共 684 行；另复核主测试和新增 6 个独立反例。
- **未评估项**：本批约定范围内 none。模型网关实现、存储实现、工具实现和网页分别属于其他独立评审批次；真实付费模型调用及效果不由 scripted adapter 测试代替。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none → Σ=0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100/100
VERDICT: Pass — assigned B3 scope has no outstanding defects
NOT ASSESSED: none within the assigned B3 scope
```

## 2. 生产事故风险推演

无待修 P0/P1。以下风险已实际验证：

1. 模型 HTTP 等待期间以原生 `asyncio.Task.cancel()` 取消：最终摘要为 cancelled，已持久化的 1032 token 预留保持未知，已知输入用量没有被伪造为消耗；没有第二次模型调用。
2. T05 实际工具调度前：观察数据库已经包含 tool_calls=1、执行链接和 claim。完成后使用工具返回的新 summary/hash，`tool_started`、`tool_completed` 各一次，报告可按任务绑定读取。
3. T05 等待期间连续两次取消运行时 task：等待工具清理结束，保存短运行报告，再结束分析；未继续调用模型。此运行时探针使用受控异步 runner 故障注入，不冒充 Docker 证明。B2 的真实 Docker 原生重复取消门禁由其独立评审记录。
4. verification 持续返回 needs_evidence：仅生成两份提案，达到候选预算后为 budget_exceeded；不得当作已完成修复。
5. 外部环境启用 LangSmith/LangChain tracing：角色调用时 tracing 仍关闭，测试拦截器未观察到 create_run。
6. 已用尽执行截止时间：模型发送次数为零，摘要为 budget_exceeded。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 已核对的承重位置

- `orchestration/runtime.py`：模型预留先持久化再 send；未知用量保留预留；工具请求授权后才调用；T05 原子 admission 回传摘要接替旧 CAS；工具完成记录后处理 `ToolExecution.cancelled`；每个角色的新上下文独立构造；最终状态由宿主设置；`tracing_context(enabled=False)` 和空 callbacks 阻止默认追踪。
- `orchestration/budget.py`：发送前检查剩余额度、调用次数、预留状态；结算拒绝 bool/负数/超过已审核上限的计量值。
- `orchestration/role.py` 与角色 prompts：结构输出经过角色解码，输入证据与源码明确为不可信数据；候选只在内存，验证不获得上一角色聊天或候选替换正文。
- `orchestration/cli.py`：模型配置来自环境而非 CLI 密钥参数；Web 无执行入口；CLI 仅输出安全摘要/固定错误；store 通过 finally 关闭。

### 实际测试证据

```text
uv run pytest tests/agents/test_runtime.py tests/agents/test_runtime_reviewer.py
20 passed in 4.06s

uv run pytest tests/agents/test_runtime_reviewer.py -k native_cancel_t05
1 passed, 5 deselected in 0.81s

uv run mypy src/agent_workbench/orchestration src/agent_workbench/agents/diagnosis/agent.py src/agent_workbench/agents/repair/agent.py src/agent_workbench/agents/verification/agent.py
Success: no issues found in 12 source files

uv run ruff check src/agent_workbench/orchestration/{runtime,budget,role,cli}.py src/agent_workbench/agents/{diagnosis,repair,verification}/agent.py tests/agents/test_runtime_reviewer.py
All checks passed!
```

第二条为第一轮之后补强连续两次原生取消的定向验证。所有测试使用独立临时 SQLite；没有读取模型密钥、发送真实模型请求、修改主数据库或操作主服务。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---:|---|
| 1 | 架构与边界 | 0 | 角色、网关、工具、存储分工；本阶段不应用补丁 |
| 2 | SOLID 与现代设计 | 0 | Adapter 接缝支持独立故障注入，未复制工具实现到角色 |
| 3 | 并发、异步与资源安全 | 0 | owner 锁、截止时间、原生取消及清理等待已验证 |
| 4 | 容错与防御性编程 | 0 | 一次结构纠正、未知状态停止、异常不会变成成功 |
| 5 | 性能与伸缩性 | 0 | 单前台、有界模型/工具/候选次数；不承诺多租户吞吐 |
| 6 | 安全与合规 | 0 | 每轮权限检查、隔离上下文、原文不入库、tracing 明确关闭 |
| 7 | 可观测性 | 0 | 固定枚举事件、摘要 revision、预留与已知用量分开 |
| 8 | 类型与契约 | 0 | 严格 DTO、mypy 通过，宿主取消字段不暴露给模型 |
| 9 | 可测试性 | 0 | 14 主用例与 6 独立生命周期/账本探针 |
| 10 | 工程规范 | 0 | 提示词版本文件、CLI 固定错误、Ruff 通过 |
| 11 | 数据与事务 | 0 | T05 返回新摘要接续 CAS，未知预留不错误清零 |
| 12 | 依赖治理 | 0 | 使用锁定环境；未增加评审依赖，LangGraph 追踪边界已探测 |

## 5. 整改清单

本 B3 范围无待整改项。工具 B2 原生取消清理修复为独立批次，本报告验证其新接口被 B3 正确接续，不重复自评其实现。

## 6. 架构防腐与长效治理建议

1. 将本次 `test_runtime_reviewer.py` 纳入常规门禁；成本为约数秒本机测试，防止 T05 摘要接续、原生取消与 tracing 边界回归。
2. 后续引入持久 checkpoint、自动 retry 或候选应用时重新评审所有外部动作的账本语义；当前图不重放，不把本批测试延伸为这些新增能力的证明。

## 7. 审计声明

- 本结论仅对 SHA 清单中已审文件有效；后续改动需要增量复审。
- 未施加豁免。
- 无 suspected 缺陷；没有将框架 API 的存在当作资源回收或执行成功的证据。
- 真实模型 A14、真实效果与父里程碑完成度不由本次 B3 Pass 代替。

## 8. A14 证据交接优化增量独立复审

2026-10-14，final_review 独立复核 `AnalysisRuntime.context`、三个 v1.1 prompt 与网关配置摘要的 `role_prompt_revision`。**Pass，100−0=100；无待修缺陷或豁免。** 本次约25行产品增量，不涉及权限、工具数/模型调用数限制或自动重试变化。

新角色获得注册表已核验的证据引用、summary 与 findings；仍不继承前一角色对话、候选 replacement 或原始 events。读取经过注册表的任务归属、引用匹配与内容 SHA 校验；不是从前一角色文字中提取“事实”。prompt 要求复用现有证据且仅补充缺失信息，仍保留全部输入不可信、不可自行授予权限、建议未经执行等边界。模型配置 hash 纳入明确 prompt revision，能区分本轮策略。payload 仍受网关64KiB硬上限，过大失败，不会静默截断证据或放宽授权。

独立新增 `tests/agents/test_runtime_handoff_review.py`：注册新证据后，新验证角色准确看到 summary/findings；前角色私有聊天与原始 events 不进入上下文；篡改已注册原文触发 ARTIFACT_MISMATCH。既有新验证上下文、权限、用量、原生取消、预算回归一同复跑：

```text
uv run --frozen pytest -o addopts='--import-mode=importlib' -q tests/agents/test_runtime.py tests/agents/test_runtime_reviewer.py tests/agents/test_runtime_handoff_review.py tests/agents/test_gateway.py tests/agents/test_reviewer_gateway.py
45 passed in 4.40s
uv run --frozen ruff check src/agent_workbench/orchestration/runtime.py src/agent_workbench/model_gateway/gateway.py tests/agents/test_runtime_handoff_review.py
All checks passed!
```

此次未调用真实模型；节省轮次的实际效果须由新 A14 记录证明，原耗尽预算的运行不能覆盖或计作成功。测试初稿一处超长行经Ruff format调整，只涉及新增测试。

最新冻结SHA（替代旧快照同名文件，包含网关prompt配置修订）：

```text
8d4439e1d81a23e1ee5e8ef9bb2a2d5193a584cf1ac71a970787e9596dfef3e6  src/agent_workbench/orchestration/runtime.py
0f2adc1f14cf021521ded6ce949754086a6141567cd95a681f303ebc47c76c4a  src/agent_workbench/model_gateway/gateway.py
c6e6e80282db42bd46bd29c139f22a00ece5ce521ea5f663e028a043c7859936  src/agent_workbench/agents/diagnosis/prompts/v1.txt
359558445c06ec33b4fde2409ccce691e1cba0183344620619a102cf4fbd86d0  src/agent_workbench/agents/repair/prompts/v1.txt
ae5b52656cbeb1e93d19f5f4387227709c524accf8942660fbe5fa70155ca209  src/agent_workbench/agents/verification/prompts/v1.txt
1cb6d1e580fba175d12b44ec6f21f21e37672370b579a37797faf9f18c1e6e21  tests/agents/test_runtime_handoff_review.py
```
