# P0-06 B3c 受控工具桥接：独立代码审计

- 审计对象：`repair_runtime/` 五个文件与两个作者测试文件，7 文件、1,405 行；外加审查者独立 5 个反例。
- 审计版本：`<review-workspaces>/p006-bridge/b3c-files.json` 的冻结清单；最终 SHA 在本报告末尾。
- 技术栈：Python 3.12、Pydantic、SQLite/SQLAlchemy、asyncio/AnyIO、固定 Docker/MCP 宿主验收器。
- 业务场景：General SaaS（实际边界为可信本机单用户、一次桥接任务串行执行）。
- 严苛度：Mission-Critical；评审时间 2026-10-14；评审者 `ui_review_density`，独立于实现者 `p006_contracts`。
- 使用 `auditing-enterprise-code-quality` skill、十二维审计矩阵及既有 P0-06 规格。未修改生产实现、主数据库，未调用模型。

## 1. 代码质量评估卡

**结论：Pass（仅 B3c 工具桥接集成门禁）。100 / 100。** 没有发现未闭功能性 Defect P0/P1/P2/P3；分数是该范围的确定性扣分结果，不代表整个 P0-06 或上线产品完成。

| P0 | P1 | P2 | P3 |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass - no confirmed functional defects in reviewed batch
NOT ASSESSED: none within B3c; model controller, CLI/API, recovery service are outside batch
```

### 实际验证

以下输出来自审查者执行，未将 mock 测试计为真实模型效果：

```text
默认作者测试：31 passed, 2 skipped in 11.99s
显式真实 Docker：2 passed in 10.33s
独立反例：5 passed in 1.73s
作者确定性 + 独立反例合并：36 passed in 8.30s
Ruff check: All checks passed!
mypy: Success: no issues found in 4 source files
```

默认跳过的 2 项已用 `AWB_CANDIDATE_DOCKER_TEST=1` 单独显式执行通过，两个场景分别实际运行 T05 + 四次 T07，共 10 个容器。正确补丁得到 `candidate_verified`，固定返回 1 的候选得到 `rejected`，cleanup 均确认 removed；`accepted` 始终 false。

确定性与真实容器命令：

```sh
PYTHONPATH=src <project-root>/.venv/bin/python -m pytest tests/agents/test_repair_tool_bridge.py tests/agents/test_repair_tool_bridge_review.py
AWB_CANDIDATE_DOCKER_TEST=1 PYTHONPATH=src <project-root>/.venv/bin/python -m pytest tests/agents/test_repair_tool_bridge_docker.py
```

## 2. 生产事故风险推演

无确认 P0/P1。重点故障推演已由独立反例覆盖：

- 快照已发布但 `finish_candidate` 数据库失败：只保留 preparing 与实际快照，返回 RESULT_UNKNOWN/需对账；再次调用被阻断，没有第二次发布。
- T05 接收后镜像版本漂移：不能标 observed_failure，不能授权 T06；没有候选创建。
- 候选树摘要错误：T07 不预留、不开容器；正确 evidence ID 搭配伪造 hash 也不能授权写操作。
- T04 请求被原生重复取消：持久终态为未知，取消标志保留，没有后台 asyncio 任务残留。
- 作者测试补充覆盖：T07 第二个 slot 保存失败后不再启动后两个容器；T05/T07 原生重复取消等待子工作清理；发布结果未知、陈旧 CAS、前置 DB 失败与两候选额度。

## 3. 详细审计明细

### P0 — none

### P1 — none

### P2 — none

### P3 — none

关键不变量核对：

- `execute` 重新通过角色 schema 解码已构造请求，授权 evidence 与正确版本；single 只读权限映射建立在新角色 schema 验证之后。
- `reserve_*` 完成后才执行 ToolRuntime、创建快照或调用 oracle。claim=None 路径不发起外部操作；持久去重与同会话完整请求摘要互补。
- 只有本次 bridge 真实 T05 的持久 observed_failure 解锁 T06；静态初始失败及新建 bridge 读取旧 T05 不授予应用权限。
- 候选必须是同任务 committed 快照。T07 宿主生成比较/执行身份，逐项先保存再继续，最终从账本重新计算。
- 反馈仅含固定规则计数与摘要，不包含隐藏 step 名、oracle 源码、输入序列；读取源码仍限制为既有授权片段。
- 未知保存状态设置 requires_reconcile 并阻止继续；其他工具失败、取消或已终止任务要求调用者停止，README 明确这一控制器契约。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 核对结论 |
|---:|---|---:|---|
| 1 | 架构与边界 | 0 | 桥接复用旧工具/账本，T05 不绕回旧 AnalysisStore；无模型循环混入 |
| 2 | SOLID 与现代设计 | 0 | 协调、反馈与 DTO 分离；领域判定仍由宿主比较器权威实现 |
| 3 | 并发、异步与资源安全 | 0 | 持有外部完整生命周期 fence、串行 busy 门禁、owned 取消回收；本地有界同步账本操作 |
| 4 | 容错与防御 | 0 | 已登记未提交结果保持未知并停止；外部错误不伪装成功 |
| 5 | 性能与伸缩性 | 0 | 上限 20 工具、2 候选、4 比较槽，有限反馈与安全清理预算；不承诺多租户 |
| 6 | 安全与数据合规 | 0 | 证据/角色/版本校验、固定源码边界、无任意路径、shell 或密钥输入 |
| 7 | 可观测与运维 | 0 | 安全状态码、持久身份与 requires_reconcile；README 指明恢复边界 |
| 8 | 类型安全与契约 | 0 | DTO 重验证、响应大小限制、mypy 通过 |
| 9 | 可测试性 | 0 | 36 确定性测试及 2 实际 Docker 测试；新增 5 独立反例 |
| 10 | 工程规范 | 0 | Ruff 与类型门禁；只读评审与实现者分离 |
| 11 | 数据与事务完整性 | 0 | 先 claim/CAS 再 I/O；失败不会重放文件或容器副作用 |
| 12 | 依赖与供应链 | 0 | 本批无新依赖、无 lockfile 修改，无自动镜像拉取 |

## 5. 整改清单

无功能缺陷整改项。工具发现的 README 示例空格格式由实现者机械修正，不作为功能发现计分。

独立测试初版两处预期已按既有契约修正：错误 evidence hash 返回 PERMISSION_DENIED；取消后的账本为 finished/outcome_unknown。它们均是安全拒绝/保守停止，未误报产品缺陷。

## 6. 架构防腐与长效治理建议

1. 后续控制器必须处理 `cancelled`、`requires_reconcile`、工具 error 与 task outcome；不得只根据 `response.status` 继续模型循环。成本为控制器状态机负向测试，避免桥接停止信号被忽略。
2. 保留快照成功、数据库失败的反例与真实错误候选测试作为门禁；防止只测试“正确修复”，漏掉副作用与回归失败。
3. 不将新建 bridge 当成恢复执行；恢复服务独立验证资源身份并对账，不能继承历史 T05 授权后续跑。

## 7. 审计声明

- 此报告允许 B3c 按冻结清单集成，不表示模型循环、P0-06 CLI/API/UI 或完整修复产品通过。
- 故障注入使用临时 SQLite 与快照，Docker 用例使用 sandbox artifacts 临时目录；主库未写入。
- 未施加风险豁免；没有 suspected 缺陷。
- 所有测试目录均在 `<review-workspaces>/p006-bridge`。独立新增文件为 `tests/agents/test_repair_tool_bridge_review.py`，应随本批集成。

### 最终冻结与格式复核

Root 代原实现者仅格式化 README 中 Python 示例；生产 Python 文件未改变。最终 `ruff format --check` 输出 `8 files already formatted`。全清单 SHA 经独立重算一致，包含新增独立测试，保存在 sandbox `b3c-reviewed-files.json`。

| 文件 | SHA-256 |
|---|---|
| `src/agent_workbench/repair_runtime/README.md` | `a97b89d615cfe4f42c16a71b30bfce96368d30fb24fbdc17f56d96df8eef5072` |
| `src/agent_workbench/repair_runtime/__init__.py` | `2417865eea3a166116395d45bd5c34d93e5e4845ff86e1eab9680db9e2ed7248` |
| `src/agent_workbench/repair_runtime/feedback.py` | `f306bcd92f1275536dd6401af5f448f7a074d81e742d7fed7c9e2fcaf23ff094` |
| `src/agent_workbench/repair_runtime/responses.py` | `512bcd972446c10eec83fe1cd1432fbf100a217a81492f3c3cdbf19145eb25d4` |
| `src/agent_workbench/repair_runtime/tools.py` | `c965a63fed1c518a9b8a1bae0d940267cd90eb9355dbbfeaf2e375cdd06975f6` |
| `tests/agents/test_repair_tool_bridge.py` | `1dac960315daf990eb4bcac0b5668040dcd0194bb9bac5d7a25d6bb7fc5347b0` |
| `tests/agents/test_repair_tool_bridge_docker.py` | `0171681a8e29c0dcadd5302e0e06320d5cec7a495d2167076697b3b730801cde` |
| `tests/agents/test_repair_tool_bridge_review.py` | `d02859fffceedac115f9e2a4411bd67e6cd399b13272f2406ee09188ce554dba` |
