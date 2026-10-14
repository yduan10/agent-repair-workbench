# P0-05b B3a 模型网关独立代码评审

- 日期：2026-10-14；工作树快照见 `P0-05b-gateway-snapshot.sha256`。
- 范围：`model_gateway/gateway.py`、其角色/预算 TokenCount 契约变更、作者 17 项测试及独立 2 项反例。依据 docs24；未参与实现。
- 方法：auditing-enterprise-code-quality；General SaaS；Mission-Critical。

## 1. 代码质量评估卡

**Pass，仅 B3a 网关模块。** 初审 Defect P1 1 项、P2 1 项均经修复和独立复跑关闭；当前 P0/P1/P2/P3 均为 0。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
INITIAL: 100 - 8 - 3 = 89; P1 cap = 79; Conditional Pass
FINAL: 100 - 0 = 100; no cap; Pass (B3a only)
```

本批不包含持久预留/结算、调用许可 CAS、LangGraph 协调、CLI 及真实网关 A14，不能由本报告推断上述批次已通过。Reply 只提供已知计数或未知标记；“保留预留”和“先结算后停止”的持久效果须由后续协调层证明。

## 2. 生产事故风险推演

G01：服务器每隔小于 read timeout 的时间发送一个字节，HTTPX 的逐次 I/O timeout 一直重置。原 `send(timeout=0.1)` 在真实本机 HTTP 探针下持续 0.292 秒后才返回无效响应；持续滴流可使单次模型请求突破总时限、占用任务 owner。该问题不需要真实模型、并发或大响应即可触发。

修复后完整 client/stream/decode 生命周期外包 `asyncio.timeout`；固定超时代码用于上层保留未知用量。外部 `CancelledError` 不被宽泛捕获。

## 3. 详细审计明细

### G01 — 整次请求缺少总期限，Defect P1，已关闭

- 初始位置：`src/agent_workbench/model_gateway/gateway.py:238`，尤其原第 246 行 HTTPX timeout 与第 264 行循环。
- 维度：3 并发/资源、5 限额；置信度 `[confirmed]`。
- 证据：独立 loopback TCP HTTP 服务每 25ms 写入 1 byte，timeout=0.1 时原实现返回 `('MODEL_RESPONSE_INVALID', 0.29206941698794253)`。
- 最小修复：整个请求范围包 `async with asyncio.timeout(timeout)`，捕获自身 TimeoutError 转固定 MODEL_TIMEOUT，外部取消保持传播。作者已实施。
- 回归：`test_drip_feed_respects_whole_call_deadline` 修复前失败、修复后通过，要求固定超时代码且耗时 <0.2 秒。

### G02 — 决策编码错误抹掉合法用量，Defect P2，已关闭

- 位置：`src/agent_workbench/model_gateway/gateway.py:185` 的 arguments UTF-8 编码及原第 189 行外层异常处理。
- 维度：4 容错、7 可观测；置信度 `[confirmed]`。
- 证据：JSON arguments 包含未配对 surrogate，usage 为合法 32+16=48。原实现将已校验计数丢弃，返回 `Reply(input_tokens=None, output_tokens=None, error='MODEL_RESPONSE_INVALID')`。
- 影响：将已知 48 token 误记为未知，宿主将保留整个输入上界预留并停止，削弱用量和故障状态准确性；没有证明实际超支。
- 修复：局部捕获 UnicodeError，保留 i/o，返回 MODEL_DECISION_INVALID。独立 `test_bad_decision_utf8_does_not_erase_valid_usage` 修复后通过。

### 核对通过

- 角色输出上限为 4096/8192/4096，受任务上限裁剪；body ≤64KiB，响应 ≤128KiB；解码拒重复 JSON key、非整数/负数/布尔 usage、总额矛盾、超预留计数。
- length 结果带合法计数与 MODEL_OUTPUT_TRUNCATED；缺 usage/超界不返回虚构计数。无自动重试，不跟随重定向，不继承环境代理；错误响应原文和 API key 不进入 Reply/config repr 或配置 hash。
- profile 显式 opt-in 且模型名有限；配置 hash 含 endpoint/model/profile/输入上界/计数语义/输出策略。它表达用户配置的条件性信任，不校验远端上游身份或网关诚实性。
- TokenCount 2M 与 Count 1M 分离；任务总量仍受已知输入+输出+预留之和校验。模型不能在本适配器中修改角色 schema。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | 配置、准备、发送、解码与编排分离 |
| 2 | SOLID | 小范围 adapter 协议，无角色实现复制 |
| 3 | 并发与资源 | G01 修复；client/response 上下文关闭，取消传播 |
| 4 | 容错 | G02 修复；传输/截断/异常用量有固定码 |
| 5 | 性能与限额 | 请求/响应字节、深度、输出、总期限受限 |
| 6 | 安全与合规 | 不回显密钥和错误 body；受信任部署假设明确 |
| 7 | 可观测性 | 已知用量与决策失败分离；无成本伪造 |
| 8 | 类型与契约 | 严格角色 schema、usage 整数、TokenCount 分离 |
| 9 | 可测试性 | 作者 17 项与独立 2 项均复跑 |
| 10 | 工程规范 | Ruff/mypy 通过，独立目录评审 |
| 11 | 事务完整性 | 本模块不写数据库；持久预留与结算由后续批次审查 |
| 12 | 依赖治理 | 本批沿用 HTTPX，无新增模型/下载；整体锁治理非本批 |

## 5. 整改清单

| ID | 级别 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| G01 | P1 | 主线程网关实现者 | B3a 交付前 | 已修复，独立复验关闭 |
| G02 | P2 | 主线程网关实现者 | B3a 交付前 | 已修复，独立复验关闭 |

无豁免。独立探针已交作者纳入默认测试；初版探针自身 Ruff 排版问题在评审副本内修正，不计产品缺陷。

## 6. 架构防腐与长效治理建议

1. 保留真实 loopback 滴流测试；它覆盖 MockTransport 或一次性响应难以证明的总期限。
2. 后续协调层断言合法 usage 只结算一次后再处理截断；未知 usage 不释放预留、不重投；该网关测试不能替代事务测试。
3. 用 profile/adapter 摘要标记信任依据；变更网关或模型时重新审查上界，不把小请求成功当成上界证明。

## 7. 审计声明

独立执行于评审副本（复用项目锁定 Python 环境、PYTHONPATH 指向副本源码），未调用外部模型、未访问凭据、未修改实现。验证命令及真实末次输出：

```text
python -m pytest -o addopts='' -q tests/agents/test_gateway.py tests/agents/test_reviewer_gateway.py
19 passed in 0.25s
ruff check src/agent_workbench/model_gateway/gateway.py tests/agents/test_gateway.py tests/agents/test_reviewer_gateway.py
All checks passed!
mypy src/agent_workbench/model_gateway/gateway.py
Success: no issues found in 1 source file
```

第一次执行误在另一评审目录运行而未找到测试，已改为正确副本后执行；不计为产品失败。初审 17 原有项通过、2 新反例失败；最终相同反例均通过。无真实 A14、账本事务或整体 Agent 有效性结论；本批所含代码范围无未审实质区域。

## 8. A14 暴露的 function 参数封装兼容修复复审

2026-10-14，独立 final_review 复核 adapter 2 增量。真实网关拒绝根联合 schema 后，实现将 `emit_decision.parameters` 改为严格 object，唯一 required 字段为 `decision`，各角色联合 schema 嵌套其中，原 `$defs` 提升到根，以保持 `#/$defs/...` 引用语义。仅在合法用量已校验后解包；重复 key、额外外层字段、非字典 decision、编码或大小不合法均保留已知用量并拒绝决策。解包后仍由原严格角色 codec/权限层校验，未绕过角色边界。

**增量结论：Pass；100 − 0 = 100，无残余缺陷、豁免或范围内未评估项。** 无新增依赖、网络目标、重试或持久字段；配置摘要已标记 adapter=2，避免混淆旧 schema 策略。

独立实跑：

```text
uv run --frozen pytest -o addopts='--import-mode=importlib' -q tests/agents/test_gateway.py tests/agents/test_reviewer_gateway.py
24 passed in 0.32s
uv run --frozen ruff check src/agent_workbench/model_gateway/gateway.py tests/agents/test_gateway.py
All checks passed!
```

另以三个角色的有效最小结论，逐一对完整参数 schema 做 Draft202012Validator 验证，再构造响应经过 `decode_reply` → `decode_role`，三个往返通过；未调用真实模型，实际网关重验由 A14 记录单列。

本次冻结 SHA-256（取代旧清单中同名文件）：

```text
6cab9814a26d43670f3aa72eedb647dd35fcce13b4048747f338c7c07caf6a1d  src/agent_workbench/model_gateway/gateway.py
e7e15e5e0fe1942fb29eadc4c1e8e84ae54ba89cf9f5ffaac6df2d38646a5e97  tests/agents/test_gateway.py
6a46d4bf82bd1a0e09068ba9d4879e26861541a9eaad493b97705a950bafc420  tests/agents/test_reviewer_gateway.py
```
