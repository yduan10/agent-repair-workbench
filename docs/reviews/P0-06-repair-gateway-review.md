# P0-06 B3b 修复模型适配独立评审

- 时间：2026-10-14；作者 Root；评审 final_review（未参与实现）。
- 范围：gateway.py 的 prepare_decision_call 抽取、repair.py 及作者测试；约250行增量。角色契约另批评审，本报告只核对适配接缝。
- 技术栈：Python / httpx / Pydantic schema；General SaaS / Mission-Critical；auditing-enterprise-code-quality。

## 1. 代码质量评估卡

**Pass，100/100。** 确认缺陷 P0/P1/P2/P3 均0；范围内无未评估文件。允许整合该模型适配模块，不等于允许省略任务预算持久化或完成模型修复实验。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (gateway increment only)
NOT ASSESSED: none within scope
```

## 2. 生产事故风险推演

无确认 P0/P1。已验证高影响路径：重复 prepare 不消费共享 schema 的 $defs；提示词不可读取、空文件、非法UTF-8及过大文件均静态报错；HTTP异常/过大响应/未知usage不会变成有结果成功，也不会暴露响应文本。适配器本身不执行工具、不判修复成功。

## 3. 详细审计明细

P0/P1/P2/P3：none，无待修项。

- prepare_decision_call 复制顶层schema后pop $defs；其余嵌套内容只序列化，不修改调用方缓存。
- 旧 DeepSeekAdapter 继续使用原角色输出上限及原config hash。独立读取可信仓库HEAD原prepare函数，与当前实现比对三个角色×四种cap×两组消息，24组 PreparedCall 全字段一致（含body字节、请求hash及预留hash）。不执行候选代码。
- 新适配四角色共同使用8192上限，较小output_cap仍生效；统一config指纹含transport配置、protocol版本、上限、全部schema和全部prompt内容hash。API key不入指纹。每个prompt/schema单独变更都改变共同指纹，适配实例构造后保持原prompt快照。
- send复用原有有界HTTP实现：无自动重试、不跟重定向、不读环境代理、期限限制及128KiB响应上限；未知用量继续unknown，截断保留有效usage。
- prompt错误只输出MODEL_CONFIGURATION_INVALID，suppress_context；未输出原异常路径或响应正文。所有prompt和schema仍须由可信宿主提供；本类不承担运行前持久化预算授权，后续控制器必须先reserve再send。

独立新增 `tests/agents/test_repair_gateway_review.py` 16项：4类prompt文件错误、4角色prompt逐一变化及实例冻结、4schema指纹变化、4类mock传输失败/未知usage边界。

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' \
  tests/agents/test_gateway.py tests/agents/test_reviewer_gateway.py \
  tests/agents/test_repair_gateway.py tests/agents/test_repair_gateway_review.py -q
```

```text
51 passed in 0.58s
HEAD prepare compatibility: 24 byte/reservation-identical cases
All checks passed!
4 files already formatted
Success: no issues found in 2 source files
```

静态检查范围为上述4文件，fresh mypy为2源文件。首个测试会话轮询时进程句柄已失效，未把未取得完整输出的该次计为通过；随后完整重跑取得上述51项结果。全部使用本地mock HTTP与合成配置，没有真实网关、Docker或模型效果测试。

## 4. 维度覆盖声明

| # | 维度 | 缺陷 | 结论 |
|---|---|---|---|
| 1 | 架构边界 | 0 | 复用既有transport，新repair协议独立 |
| 2 | SOLID设计 | 0 | 单一请求builder，旧适配器向后兼容 |
| 3 | 并发资源 | 0 | schema缓存不修改；复用有界client/timeout |
| 4 | 容错 | 0 | 静态错误、usage unknown保留、无自动重试 |
| 5 | 性能 | 0 | 构造时读取有限prompt；请求/响应有界 |
| 6 | 安全合规 | 0 | key隐藏、错误不泄正文；无工具执行 |
| 7 | 可观测性 | 0 | config/request/reservation指纹可追踪 |
| 8 | 类型契约 | 0 | RepairAdapter Protocol与统一PreparedCall/Reply |
| 9 | 测试性 | 0 | 16独立反例与24组旧请求精确比较 |
| 10 | 工程规范 | 0 | Ruff/format/mypy通过 |
| 11 | 数据事务 | 0 | 无DB写入；持久预留由调用方承担 |
| 12 | 依赖治理 | 0 | 无新增依赖，frozen环境验证 |

## 5. 整改清单

none，无豁免，无实现变更。

## 6. 长效治理建议

1. 后续repair runtime接入必须断言发送前已持久预留，以及single/three_role采用相同总预算；成本为控制器边界反例，不能由本适配器等额上限替代。
2. 保留旧请求hash及schema缓存反例，每次协议版本变更同步指纹门禁；无需引入额外依赖。

## 7. 审计声明

只对下列冻结文件版本成立。其他评审者负责角色契约正文；本报告不重复承诺完整工具权限或模型任务闭环。没有修改生产代码/数据库，未访问真实网关，未运行Docker。未知用量和条件性模型上界依然沿用P0-05限制，调用前预算控制须后续集成验收。后续代码修改需增量复核。

```text
bde4a7f14a7ef94a8c3d5b3701a04f0adbb44d65691edd80e9468474951bd81c  src/agent_workbench/model_gateway/gateway.py
96cce487259d01db66f7a9a0d00b32706f998e3cbe90f71e612ff11f4c45e169  src/agent_workbench/model_gateway/repair.py
c6dc659bdc1dcab66f72fc6e061b1cfae8c211ace78c051d1a641600f71464f1  tests/agents/test_repair_gateway.py
6046047183914c54795d6ef0981307db3d3b1346a92828fd7cd698a20a989708  tests/agents/test_repair_gateway_review.py
```
