# P0-01 独立代码审计报告

- **审计对象**：src/agent_workbench、tests、pyproject.toml、uv.lock、CI；对照 AGENTS、01/03/04/05 规格，复核 06 依赖记录。
- **审计版本**：工作区 SHA-256 清单见末尾；本地仓库尚无提交。
- **技术栈**：Python 3.12、Pydantic、jsonschema、multiprocessing、uv、pytest/Hypothesis。
- **场景 / 严苛度**：General SaaS / Mission-Critical。
- **审查者**：`/root/code_review_m0`，独立只读子 Agent；主 Agent 保存报告。
- **日期**：2026-10-13。

## 1. 代码质量评估卡

**P0-01 本地开发里程碑：Pass。** 当前限定范围无未解决 Defect P0/P1/P2/P3。它可以作为下一项工作的基础，不构成公共发布、生产运行或完整 Agent 产品认证。

初审独立发现并复现 1 项 Defect P1；实现者修复后已独立复审。

| 未解决 P0 | 未解决 P1 | 未解决 P2 | 未解决 P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
INITIAL: 100 - 8 = 92; P1 cap 79; Conditional Pass
CURRENT DEDUCTIONS: 0 (CR-01 fixed and re-reviewed)
CURRENT SCORE: 100 / 100
VERDICT: Pass, P0-01 local development only
NOT ASSESSED: remote CI, Linux host execution, isolated build supply chain,
              public package installation, M1/M2 tools and models
```

未评估项目不属于 M0 实现门禁，仍阻断相应发布/后续阶段通过结论。分数不能解释为整产品完成度。

评审者实际输出：

```text
uv run --frozen pytest
86 passed in 2.32s

uv run --frozen ruff check .
All checks passed!

uv run --frozen ruff format --check .
19 files already formatted

uv run --frozen mypy
Success: no issues found in 5 source files

uv lock --check
Resolved 25 packages in 3ms
```

评审者额外独立构造：8 种子 schema 位置 `$ref` 全部拒判；结果 ID 错配优先于 is_error；36 组小数/因子组合（含负数、极小数、嵌套 dialect）与 Fraction oracle 一致；5 组原始精度反例修复后拒判。

## 2. 生产事故风险推演

**CR-01，已关闭。** JSON 浮点转换先损失精度，默认 multipleOf 再发生舍入错误，会令合法输入失败或非法输入通过。影响单次检查及依赖它的后续修复验收。原 68 项测试未覆盖，独立反例检出，已加入回归。

| 输入 / 约束 | 原结果 | 应有结果 |
|---|---|---|
| 0.3 / multipleOf 0.1 | failed | passed |
| 0.07 / multipleOf 0.01 | failed | passed |
| 原始 JSON 1e-999 / const 0 | passed | 不得通过 |
| 原始 JSON 9007199254740993.0 / const 9007199254740992 | passed | 不得通过 |
| 原始 JSON 0.10000000000000001 / const 0.1 | passed | 不得通过 |

## 3. 详细审计明细

### Defect P0

none。

### Defect P1

**CR-01：数值精度导致确定结论错误 — confirmed，已修复。**

- 原位置：checker.py:51–55、110–119；原快照 SHA-256 `a1552c68f3ff6b86cf60691c1c74ad25b4bd641073cb8f8185f8654e11743904`。
- 维度：类型安全/契约与数据正确性；违反 C-03 及 P0-01 结果语义。
- 当前修复：checker.py:59–67 Decimal 保真；70–89 精确 multipleOf；144–152 防止嵌套 `$schema` 将验证器切回默认实现；255–256 返回 unsupported_number。

最小修复策略（语义摘要）：

```diff
- 浮点转换后直接认定可检查
+ 十进制往返及整数值精度检查；无法保真则拒判
- multipleOf 使用默认浮点运算
+ Fraction(str(instance)) / Fraction(str(divisor)) 判断整除
- 嵌套 $schema 可重新选型验证器
+ 已确认唯一 dialect 后，仅在 schema 位置的副本移除该标记
```

复审：已消除确认的误判；0.30000000000000004 不因 epsilon 放行。数字支持边界已写入规格。

### Defect P2

none。

### Defect P3

none。实现者另行修复的报告顺序一致性、CLI 非法参数回显，独立 reviewer 已检查增量和测试。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构 | CLI、模型、纯检查分离；M0 范围清楚 |
| 2 | SOLID | 当前规模无必须添加的抽象 |
| 3 | 并发资源 | 单 worker；真实进程超时、崩溃、先报告后崩溃测试；句柄释放已读 |
| 4 | 容错 | 不支持、缺失、异常、超时均不通过 |
| 5 | 性能 | 文件/节点/深度/findings/时间有界；嵌入 API 由调用者隔离 |
| 6 | 安全 | 不回显原始值、不获取 schema 引用；路径敏感性已声明 |
| 7 | 观测 | 状态、错误码、路径、版本、摘要；M0 无后台服务 |
| 8 | 类型契约 | 严格 envelope；CR-01 已关闭 |
| 9 | 测试 | 86 项含 CLI 子进程与故障；额外独立反例通过 |
| 10 | 规范 | Ruff/mypy/锁检查通过；优先级和严重度分离 |
| 11 | 数据 | 哈希及报告复核；无数据库事务/迁移 |
| 12 | 依赖 | 锁、CI SHA、许可证、运行环境扫描已查；构建环境属于发布门禁 |

独立 reviewer 直接读取依赖扫描 JSON：23 个依赖无已知漏洞，本地包跳过公告检查。另核对 7 个运行/开发直接依赖安装元数据，版本及许可证一致。没有独立扫描 hatchling 隔离构建环境。

## 5. 整改清单

| ID | 等级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| CR-01 | Defect P1 | 实现者 Codex | P0-01 done 前 | fixed，独立复审通过 |

无剩余整改项。

## 6. 长效治理

1. jsonschema 升级必跑数值和嵌套 dialect 回归，防止静默误判。
2. 后续真实 MCP 沿用拒判语义，不将缺结果/传输错误转为成功。
3. 公开分发前完成构建环境锁定/扫描、安装、远端 CI，不能由本报告替代。

## 7. 审计声明与快照

无风险豁免，无 unresolved suspected 项。源码或验收规范变化后审增量。以下为 reviewer 提供的最终快照：

```text
2a45cd6bb82bf1681ce96ec030853d4ed28a44f23117b8f0149bae4a37878ec1 .github/workflows/checks.yml
bbed65f96649c0a930e8e1aca3186b1fa2239fb259694722a988bbdc9b9697b0 docs/05-contract-checker.md
9242609ba7afe55ea12039c06aa2900099ca1fe071ccb95204aeb154019ec5f7 docs/06-dependencies.md
f293b51796425aca7b2e8862eb25062bfd9cdb1a6db71353dcf71b8d50cdb75a pyproject.toml
a574a68f8a08b6c1d76b5599cb86d06bc263ab4f74feb0327ab13e3a3212d137 src/agent_workbench/__init__.py
b26cda2a0eaef57cf8d7ffe7670228544e12cfa6c4c42997e03ea70ef4ee2dcf src/agent_workbench/__main__.py
e8e0b0d5948f1330e13fb8bd1bf6a36f958c550cad86975c7bea72c229207966 src/agent_workbench/checker.py
f1e1221bff40965ea418acd39575ca06e60945f0642249a548781fdb639de7c1 src/agent_workbench/cli.py
59bd1d98a11fa1192bd15d90b7fb2d8976553888db1a42865143095f9929e6aa src/agent_workbench/models.py
c9a00196db77224f996657764f6962aa58bc8a9937d86f4cb67e3b7174ee2c63 tests/conftest.py
a8e7b62fe45d9116c4d5592a167882a236524904c2f24266e3a032ae903b3681 tests/test_checker.py
d8cbe8d6cb8220e89e272c1fbea012e2abc1a4ae1dd5b36bd1e7a4000e875e4e tests/test_cli.py
997dce806462bc3d57996ea31afcb7f296148de80d550dcd92995aab1f68d51b uv.lock
```
