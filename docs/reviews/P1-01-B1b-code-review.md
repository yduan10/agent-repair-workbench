# 企业代码质量审计报告：P1-01 B1b

- **审计对象**：`RepairController.run_created`、公共循环、持久取消、接收时间预算、held-fence 对账、安全释放。
- **审计版本**：基于 `40d3e34662dfbe684cf2f3f1581f4db213df0204` 的 B1b 工作树；准确生产源码 SHA-256 见文末。
- **技术栈**：Python 3.12、asyncio/AnyIO、LangGraph、SQLite/SQLAlchemy、POSIX flock、受控 Docker CLI。
- **业务场景**：General SaaS；本机可信单用户内部执行接口。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15。
- **独立评审者**：Codex 子 Agent `/root/b1b_review`；未实现生产代码。使用 `auditing-enterprise-code-quality`，读取冻结规格 35、约束及台账。

## 1. 代码质量评估卡

- **当前综合质量得分**：100 / 100；只表示本次有界范围无已确认未修缺陷，不表示整个产品不存在缺陷。
- **评审结论**：**Pass（B1b 生产代码复审）**。先发现的取消收尾缺陷已修复并独立复测；本报告不能替代全量测试、前端进度和交付文档门禁。
- **审计范围**：8 个生产文件，约 720 行新增/修改/删除；新旧核心回归及 3 个独立反例。
- **范围外/未评估**：B2 HTTP/lifespan、多 worker 资源组合，B3 页面操作，B5 真实网关和真实 Docker 端到端。不把本次确定性测试当作真实修复成功率。

| 未修 Defect P0 | 未修 Defect P1 | 未修 Defect P2 | 未修 Defect P3 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
INITIAL: P1 x 1 = 8; raw 92; P1 cap 79; Conditional Pass
CURRENT DEDUCTIONS: 0 (P1-1 fixed and independently retested)
CURRENT SCORE: 100 / 100
VERDICT: Pass within B1b production scope
NOT ASSESSED IN SCOPE: none
```

## 2. 生产事故风险推演

**P1-1：上层取消后收尾再次被取消，丢失已经结算的控制器返回值。**

- 触发：`run_created` 的上层任务取消；外层 `_owned` 将取消转为 AnyIO owner scope 取消。
- 机制：业务 `_loop` 已捕获取消并写入结算，但 `_watched_loop` 的 `finally` 再次执行未屏蔽的 `await gather(watcher)`，已取消 scope 在此检查点再次抛取消。
- 用户可见结果：调用方得不到 `RepairResult`，无法按正常受控取消路径继续处理；不能把账本可能已结算解释为返回成功。
- 爆炸半径：一个网页修复任务；未证实重复发送或提前释放资源。
- 可检测性：新增 `test_parent_cancel_keeps_fences_until_model_settlement` 可稳定覆盖连续两次取消；修复前失败，修复后通过。

## 3. 详细审计明细

### Defect P0 — none

### Defect P1 — P1-1 已修复 [confirmed]

- **位置**：`src/agent_workbench/repair_runtime/controller.py:396`，`_watched_loop` 收尾。
- **维度**：3，并发、异步与资源安全。
- **问题分析**：见上节。外层取消 scope 必须允许已开始业务完成结算，并等待 watcher 清理，不能在最后一个 await 丢弃结果。
- **最小修复**（实现者完成）：

```diff
 finally:
     watcher.cancel()
-    await asyncio.gather(watcher, return_exceptions=True)
+    with anyio.CancelScope(shield=True):
+        await asyncio.gather(watcher, return_exceptions=True)
```

- **独立复测**：连续父任务取消、模型未知用量保留、两把 fence 在清理期间仍不可被接管，返回 `RepairResult.cancelled=True`；通过。

### Defect P2 — none

### Defect P3 — none

初次执行时新测试夹具误传 `load_repair_case(intent=...)`；旧 recovery 反例仍 patch 已不使用的 wrapper。实现者已修正夹具并迁移到 held 接口注入，保留“接管锁被拒绝”和 stale CAS 的实际断言。这是测试调试记录，不计为生产缺陷。

## 4. 维度覆盖声明

| # | 维度 | 当前发现数 | 说明 |
|---|---|---:|---|
| 1 | 架构与边界 | 0 | 网页只取得一次执行权；沿用公共角色/工具循环，未新增自主修复路径 |
| 2 | SOLID 与现代设计 | 0 | 对账 wrapper 与 held 核心共享原实现；恢复资源检查与事务提交分离 |
| 3 | 并发、异步与资源安全 | 0 | P1-1 已关闭；web→task guard 持续覆盖执行、结算与清理 |
| 4 | 容错与防御性编程 | 0 | 未知创建不能凭 absent 解锁；错误保留 active，无强制跳过路径 |
| 5 | 性能与伸缩性 | 0 | 固定预算/串行调用/有界身份清单；非多租户吞吐结论 |
| 6 | 安全与合规 | 0 | 只删除精确身份容器；失败响应不输出原始路径或 Docker 异常 |
| 7 | 可观测性 | 0 | 保留原事件、用量与未知历史；释放状态与 recovery report 分离 |
| 8 | 类型安全 | 0 | 接收 claim/Mutation/fence 绑定及报告结构沿用严格契约 |
| 9 | 可测试性 | 0 | 临时真实 SQLite/快照，脚本模型及明确 Docker double；反例进入 CI |
| 10 | 工程规范 | 0 | 本批范围受控；未知创建保守阻塞符合冻结规格 |
| 11 | 数据与事务完整性 | 0 | 完整 receipt/task/request/candidate/report/event 摘要最终 CAS；取消、预算不被恢复重置 |
| 12 | 依赖与供应链 | 0 | 无新增第三方依赖，无模型下载 |

## 5. 整改清单与验证证据

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P1-1 | Defect P1 | Codex 实现 Agent `/root` | B1b 完成前 | fixed，独立复测关闭 |

独立执行：

```bash
uv run --frozen pytest tests/test_web_repair_execution.py tests/test_repair_recovery.py tests/agents/test_repair_controller.py tests/agents/test_repair_controller_review.py -q
# 84 passed，exit 0；原始输出 artifacts/b1b-independent-followup.log

uv run --frozen pytest tests/test_web_repair_b1b_review.py tests/test_web_repair_execution.py -k 'parent_cancel or last_inspect or cancel_recovery or historical_claim'
# 4 passed, 26 deselected in 3.09s

uv run --frozen ruff check tests/test_web_repair_b1b_review.py
# All checks passed!
```

独立新增的 `tests/test_web_repair_b1b_review.py` 覆盖：

1. 最后资源检查阶段变更 receipt（task revision 不变），最终 evidence CAS 仍拒绝释放。
2. 恢复检查协程被取消，清理期间两把 fence 不可接管，active 保留。
3. 另建 Controller 重用历史 admission claim，零新增调用且拒绝重入。

原始试验记录位于忽略目录 artifacts；可重复测试已写入 tests，由正常 pytest 发现。未迁移用户主库、未调用真实模型、未发起外部发布。

## 6. 架构防腐与长效治理建议

1. 保留“unknown create + absent”和“缺报告 + 精确迟到容器被移除”的成对回归，新增执行后端必须各自提供终结依据。成本：现有测试维护。
2. B2 接入时对 shutdown、HTTP 断连和父任务连续取消继续复用本次所有权模式；扩展测试而非复制执行循环。成本：B2 生命周期测试。
3. B2 不以本次单修复槽测试宣称复现/分析/修复组合总量已得到保证；沿规格 35 的组合故障门禁执行。

## 7. 审计声明

- 此结论仅适用于下列生产源码哈希。后续生产变更须复审；文档测试数量以后续完整交付报告为准。
- 已施加豁免：none。
- 保守限制：CLI `apply` 成功、PID 消失、重复 absent 都不是创建终结依据；某些 SIGKILL/缺报告场景继续占用 active 是契约行为，不能宣称全部可恢复。
- 额外测试不能证明真实模型效果、跨进程 HTTP 行为或商业使用质量。

| 生产文件 | SHA-256 |
|---|---|
| repair_runtime/controller.py | `c0f2e6a6ea55a581f8200c17aaa4dc588dd8d04754c972da41f0ef01c0ba106a` |
| repair_recovery/service.py | `670ea4764bd9c365d7782d53ae97a2a9958bce5701c1bfb9b9d82eebfaa9c298` |
| repair_store/store.py | `ca59cb4cc67e012c08ad6bf171079cd18fb4549aab6726b875c247a87d0e8783` |
| repair_store/comparisons.py | `9fc8622c89161a053169e402245ea0b54a00ec33fa50d49b5cb8102605773f4d` |
| repair_store/reproductions.py | `33fb9ea3b6048273b744ea70ee18ef0cd0460434c51a2c46d8df7836f1469979` |
| web_repairs/store.py | `d7faefb425f426a8c365b346f252835715d00270adcc3c5f472f674897bf3aeb` |
| web_repairs/policy.py | `58215ba3ade75e726767ec7383d8f3929f40a8aa272ee57bd74193ee35540b56` |
| web_repairs/recovery.py | `c19dddfc5685d52b80967e32b181b2b07b24d5c6c6428902b8f59815241cdb06` |

## 8. 交付文档与前端进度一致性核对

2026-10-15，独立只读复核 README、台账 03、规格 34/35、交付记录 37，以及 `frontend/lib/{capabilities,documentation,milestones}.ts`。

- 修复能力仍为 `web_readonly`；未增加可执行按钮、未把内部执行标成网页可用。
- README/交付文档明确 B2 API、B3 页面操作与 B5 真实链路尚待实施，未用脚本模型/Docker double 冒充真实修复效果。
- 37 明确 absent/旧 CLI apply/PID 消失不能证明 create 终结；缺报告且有精确回收证据才可释放，T06 未决及 T07 部分证据保守占槽。主库 0007 未迁移与后端未切换也已说明。
- 前端新增站内工程记录链接，并更新用户可理解的文档变更说明；未在产品能力标记上露出测试数量或里程碑编号。
- 初核发现两处文案同步项：35 首行旧状态“B1b尚未实施”应更新；37 表格“接收前停止零调用”应准确表述为“消费前已登记停止零调用”。这是文档修订项，未发现新的生产代码缺陷。
- 本核对不替代正在执行的 Chrome 链接验收；最终 done 必须在该项通过后同步台账、35、37、README 及前端注释。

**最终一致性复核：Pass。** 上述两处文案已修正；35 首行与 37、台账明确 B1a/B1b 内部实现已验收，37 停止语义已改为“消费前已登记停止零调用”。已读取 Chrome 实际日志：`1 passed (12.8s)`、127 页、120 个交叉链接、`broken: []`。README、34/35/37、台账及前端注释已同步最终状态，父 P1-01 仍 in_progress，`repairs.status` 仍 `web_readonly`，B2/B3 尚未开放。无待修文档一致性问题；最终前端重新构建用于包含本评审追加内容。
