# 企业代码质量审计报告

- **审计对象**：P0-06 B3d 受控修复模型循环与上下文构建。
- **审计版本**：独立目录 `agent-sandboxes/p006-controller`，冻结清单 `artifacts/b3d-files.json`；最终 controller 摘要 `b87603b3ea39f669c520bfb22b56f1e252d8ba5f4f93e1b32f73d6a9531603fd`。
- **技术栈**：Python 3.12、LangGraph、Pydantic、SQLite、POSIX owner fence。
- **业务场景**：General SaaS；固定公开案例、本机可信单用户工具。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14（Asia/Shanghai）。
- **独立评审者**：p006_contracts；未参与 controller/context 实现。使用 auditing-enterprise-code-quality。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，修复后本批无已确认未解决缺陷，非整体产品评分。
- **上线评估结论**：**Pass：允许 B3d 整合**；不是 P0-06 全部验收或真实模型修复能力证明。
- **审计范围**：controller、context、README 增量、作者测试，共 4 文件约 930 行；新增 1 个独立反例文件。已审工具桥接、账本和 oracle 仅检查调用接缝，不重开其实现评审。
- **未评估项**：范围内 none。CLI/API、精确恢复入口、真实模型与 Docker 组合效果、网页由后续批次分别验收；作者并行新增的 B3e 不在本报告范围。

| 未解决 P0 | 未解决 P1 | 未解决 P2 | 未解决 P3 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none remaining -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (B3d only)
VERDICT: Pass after cancellation admission fix
NOT ASSESSED: later CLI/API/recovery/UI and real model/container end-to-end
```

## 2. 生产事故风险推演

### 已收到取消，但仍启动下一外部操作（已修复）

- **触发条件**：当前节点的 Task.cancel 已生效于取消计数，但尚未经过异步检查点；分别发生在模型预留事务结束后、模型结算事务结束后。
- **失效机制**：原实现依赖下一次 await 交付 CancelledError，先构造了 owned sender 或执行下一工具。owned 会等待并清理子工作，但不能替代“取消后不得开始新工作”的准入检查。
- **症状**：预留后取消仍进入模型 send 一次；结算后取消仍启动 T05 oracle 一次。既有预算不被绕过，但取消已知情况下仍会产生新的成本或容器操作。
- **爆炸半径**：单任务的下一次模型/工具操作。
- **可检测性**：独立反例在原冻结版本两处均实败；修复后零新增 send/attempt。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### C-1. 模型与工具边界缺少已知取消检查 — 已修复

- **位置**：`src/agent_workbench/repair_runtime/controller.py:111`、`:139`、`:185`。
- **审查维度**：并发与资源安全、执行权限、容错。
- **置信度**：[confirmed]。
- **问题分析**：原 `reserve_model → _owned(send)` 和 `settle_model → bridge.execute` 间未检查 `asyncio.current_task().cancelling()`。注入取消后，前者 adapter.calls=1，后者 ctx.attempts 有一个已登记的新 oracle。
- **最小修复**：新增 `_check_cancelled()`，在模型准备前、预留前、预留后 send 前、模型返回后 tool 前检查。用内部 Halt 传递取消，避免依赖 LangGraph 对子节点原生 CancelledError 的传播方式。

```diff
+ def _check_cancelled(self) -> None:
+     task = asyncio.current_task()
+     if task is not None and task.cancelling():
+         self._cancelled = True
+         raise Halt("cancelled", "CANCELLED")
```

- **账本处理**：已持久预留的调用不凭空删除，按 MODEL_CANCELLED 的未知用量结算并停止，保留预算；预留后期限耗尽使用 MODEL_TIMEOUT，不误记用户取消。未持久确认的提交保留最后已确认 cursor 与 requires_reconcile。
- **验证**：独立测试 `test_cancel_after_reservation_never_enters_adapter_send`、`test_cancel_after_settlement_never_starts_proposed_tool` 修复前失败，修复后通过。其余原生重复取消清理测试仍通过。

### P2 — 主要缺陷

none remaining。

### P3 — 次要缺陷

none。

### 验证证据

全部操作位于独立目录，SQLite 和快照为 pytest 临时数据；模型、oracle 使用明确合成实现。没有写主库、没有真实模型费用、没有将合成 oracle 当作 Docker 通过。

原冻结批次的调用接缝回归由评审者独立执行：

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_controller.py tests/agents/test_repair_tool_bridge.py tests/agents/test_repair_gateway.py tests/agents/test_repair_contracts.py -q
```

```text
179 passed in 18.70s
```

取消修复后，作者 26 项 controller 测试 + 当时 6 项独立测试：

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_controller.py tests/agents/test_repair_controller_review.py -q
```

```text
32 passed in 13.09s
```

随后针对作者最后的超时/取消区分增量增加第 7 个独立测试，并重跑完整独立文件：

```text
7 passed in 3.65s
```

独立反例覆盖：

1. 同一 RepairFence 覆盖全部模型、T05、4 个 T07 slot，运行期间第二 owner 不能获得锁。
2. 模型预留已 commit 但确认丢失，不发送模型；实际库 model_pending，返回最后已确认 ready cursor 并要求对账。
3. 模型结算已 commit 但确认丢失，不启动模型提议的工具；实际库 ready，返回 model_pending cursor 并要求对账。
4. 结算后取消，不开始新 T05；模型调用结算仍存在。
5. 预留后取消，不进入 adapter.send；已预留计量按未知保留。
6. 重复原生取消期间 sender 延迟清理，owner 锁始终保持，确认 sender 退出后才释放。
7. 预留后时间耗尽，不发送模型、不误标 cancelled，保留未知预留。

格式、静态和类型检查：

```text
All checks passed!
3 files already formatted
Success: no issues found in 2 source files
```

以上分别来自对 controller/context/独立测试的 Ruff、format 检查，以及 controller/context 的 `mypy --no-incremental`。

## 4. 维度覆盖声明

| # | 维度 | 未解决发现 | 说明 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | controller 只编排，账本授权执行，bridge 执行工具，oracle 决定验证结果 |
| 2 | SOLID 与设计 | 0 | 上下文构建独立；模型适配器协议注入；未复制旧 Agent 实现 |
| 3 | 并发与资源安全 | 0 | C-1 已修；全生命周期 fence、重复取消等待清理、一次性 controller |
| 4 | 容错 | 0 | 预留/结算/终态不确定不重发，显式 requires_reconcile，不续跑旧 task |
| 5 | 性能与效率 | 0 | 模型/工具/两候选/总时长预算同账本；上下文与请求字节有界；无无限循环 |
| 6 | 安全与合规 | 0 | 只有授权资料与固定聚合规则进入 context，隐藏 oracle 输入/step/replacement 不进入；无任意路径或命令 |
| 7 | 可观测性 | 0 | 持久 reserve/settle/真实 host 结果；静态错误码，不保存模型原文；没有捏造恢复成功 |
| 8 | 类型与契约 | 0 | role codec、准备请求 hash/大小、资源引用复核；configuration hash 漂移停止 |
| 9 | 可测试性 | 0 | 26 作者测试与 7 独立故障交错；合成与真实执行证据明确区分 |
| 10 | 工程一致性 | 0 | 新包沿现有共享运行时边界；README 明确内部入口与尚未接通项 |
| 11 | 数据与事务完整性 | 0 | CAS + claim 先行，模型 ID 宿主生成、工具 ID 原样保留，同参回放无新副作用 |
| 12 | 依赖治理 | 0 | 本批无新增依赖或自动下载镜像；不重跑全项目供应链扫描 |

单角色与三角色使用同一预算、工具权限总集合与输出上限。三角色根据真实 T05/T06/T07 路由；最多两候选。此结构不证明三角色更有效，仍需真实模型对照实验。

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| C-1 | Defect P1 | final_review（实现者） | B3d 整合前 | 已修复、独立复审通过 |

## 6. 架构防腐与长效治理建议

1. 保留取消与事务确认丢失的独立反例为回归门禁，后续新增外部副作用同样检查“已知取消不得准入”。成本为维护现有 7 项测试。
2. 下一批 CLI/API 不可把 `requires_reconcile=True` 或 ready/pending cursor 显示成已完成，更不能重新创建相同任务续跑；恢复需独立验收。
3. 模型实验同时记录 single/three 的全部失败、未知和实际消耗；此处的合成通过率不可替代真实修复效果。

## 7. 审计声明

- 原冻结 controller `ad71c861...` 存在已确认取消缺陷；仅下列最终版本获准整合。
- 本报告不覆盖 B3e CLI、后续恢复、网页和真实模型评估；上述工作仍需各自测试与独立评审。
- 豁免 none；无 suspected 发现用于门禁。
- 独立测试 `tests/agents/test_repair_controller_review.py` SHA-256：`6272e78e58b319bb490eb4d056c21695131392fee13aa0d02c7648df745e1332`。

```json
{
  "src/agent_workbench/repair_runtime/controller.py": "b87603b3ea39f669c520bfb22b56f1e252d8ba5f4f93e1b32f73d6a9531603fd",
  "src/agent_workbench/repair_runtime/context.py": "b274607634f042e34ddce45f1af0288713297fb1adef6ddfbf0c4d2900742baa",
  "src/agent_workbench/repair_runtime/README.md": "bf9146710fff04c055b982226d5893dcb8c4c33b28981e938f6e7da2714ab1f7",
  "tests/agents/test_repair_controller.py": "fa13e92c1b4a318860accf201e8c14e2ef0599caf63fc6c124a368529109efdb"
}
```
