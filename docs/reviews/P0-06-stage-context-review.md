# 企业代码质量审计报告

- **对象**：P0-06 context/prompt 1.4 阶段绑定小增量。`context.py`、4 角色 prompt、作者测试增量及独立反例；controller 仍为已审 1.3 SHA。
- **评审者 / 日期**：p006_contracts（未参与实现）/ 2026-10-14；使用 auditing-enterprise-code-quality。
- **场景 / 严苛度**：General SaaS / Mission-Critical。

## 1. 代码质量评估卡

**Pass：允许冻结版本进行真实模型实验。100 / 100，无未解决确认缺陷。** 分数仅对应本批审查；不保证真实模型会遵循阶段提示，不证明多 Agent 优势。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none remaining -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (stage-context 1.4 only)
VERDICT: Pass
NOT ASSESSED: real model success rate, holdout generalization
```

P0/P1/P2/P3 未解决项均为 0。真实模型效果与独立保留变体不在本批评审内。

## 2. 生产事故风险推演

- 新候选生成后继承旧候选的 rejected：当前比较进度必须按 candidate_id 对齐；旧比较结果只作为带 ID 的历史素材保存。
- verification 得到未来候选创建参数后误操作：application binding 在验证阶段为 null；比较绑定直接指向已 committed 候选，不能用 next_candidate_id 比较。
- 模型提前 handoff：角色文案明确 T05/T06 后宿主自动转阶段，T07 后宿主决定后续或结束；权限和验证仍由原 controller/tool bridge 执行。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

无未解决项。

### P2 — 主要缺陷

无未解决项。

### P3 — 次要缺陷

none。

### 审阅中修正并复核的两处不一致

1. 最初 next_stage 已按候选 ID 区分旧拒绝，但 `execution_progress.comparison_status` 仍直接展示旧比较状态。实现者已改为 ID 与当前候选相同才返回状态，否则为 null。独立单/三角色真实临时账本测试确认：第一次候选 rejected，第二次候选未比较时 next_stage=compare_candidate 且 comparison_status=null；旧结果仍带第一候选 ID 保留。
2. verification prompt 仍有 otherwise handoff 旧指令。实现者已替换为存在 comparison binding 就请求比较，宿主决定后续角色或收束。未扩大模型权限，也未改变验收条件。

这两处在正式冻结测试前修正；没有把未运行的修改前反例写成失败测试记录。

### 验证证据

```sh
uv run --frozen pytest tests/agents/test_repair_stage_review.py tests/agents/test_repair_context_review.py tests/agents/test_repair_controller.py tests/agents/test_repair_controller_review.py tests/agents/test_repair_gateway.py -o addopts='--import-mode=importlib' -q --tb=short
# 77 passed in 22.80s
```

新增独立 18 项：单/三角色各一次旧拒绝→新候选隔离检查；4 角色 × 4 阶段绑定可见性矩阵。其余 59 项为上下文纠错、controller 和 gateway 已有回归。全部使用临时数据库、真实快照及合成模型/oracle，没有主库或真实模型调用。

```text
All checks passed!
2 files already formatted
Success: no issues found in 1 source file
```

分别为 context 与独立测试 Ruff/format，以及 context fresh mypy。

## 4. 维度覆盖声明

| # | 维度 | 发现数（未解决） | 核查结果 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | next_stage 是提示，不替代宿主权限或验证 |
| 2 | SOLID 与设计 | 0 | 仅 context 组装与角色提示变化；原控制器不变 |
| 3 | 并发与资源安全 | 0 | 无新并发/生命周期变动，沿用已审 fence |
| 4 | 容错 | 0 | 旧比较与当前候选明确隔离，不把已提交当通过 |
| 5 | 性能 | 0 | 固定小字段增量，48 KB 上限保持 |
| 6 | 安全与合规 | 0 | 分角色/阶段 binding；不新增隐藏 oracle 数据或任意路径 |
| 7 | 可观测性 | 0 | 当前阶段、当前比较与带 ID 历史素材分开 |
| 8 | 类型与契约 | 0 | binding 字段对应现有 schema；权限/schema 未变 |
| 9 | 可测试性 | 0 | 18 独立矩阵/状态用例及 59 回归 |
| 10 | 工程规范 | 0 | 4 prompt 同步 1.4；明确自动路由和提前结束语义 |
| 11 | 数据与事务完整性 | 0 | 不改持久化，比较状态按当前 candidate ID 关联 |
| 12 | 依赖与供应链治理 | 0 | 无新增依赖与外部访问 |

## 5. 整改清单

两处审阅意见已修复并复核，无遗留整改。

## 6. 长效治理建议

1. 保留阶段/角色矩阵及旧比较隔离测试，后续上下文缓存不要只按工具名称解释当前状态。
2. 若希望禁止单角色在未比较时创建下一候选，需要单独设计宿主 admission 规则。本批只改提示，不宣称已经增加此强制限制。
3. 真实实验按冻结版本完整报告，包括失败；本轮评审不能替代模型修复效果与公平对照。

## 7. 审计声明与版本

只读生产源码，新增独立测试/报告/哈希清单。controller SHA 保持 `702ca5bd1eae5b5fa0c192ae913c6fa5c1d0a9ef225d8f62fe9ec2d85bec9f8b`。无豁免。

```json
{
  "src/agent_workbench/repair_runtime/context.py": "4185af4192c0d1d7d4658deed2735ddfdfc71fcb9189bcd2e34e6131333b9779",
  "src/agent_workbench/agents/diagnosis/prompts/p006.txt": "7f0c216c75562c90ad8066e4affd7039960c091bea2b7d9f6053b85703ceb06d",
  "src/agent_workbench/agents/repair/prompts/p006.txt": "5f7033c38e181747f17758ba28a4ee648e3bf456b1391f941b20c5cdcece7d7d",
  "src/agent_workbench/agents/verification/prompts/p006.txt": "d787003722ccfddbeb5a019d3ce3d65e5ad4a520a4944401bdf9254e333f6fc2",
  "src/agent_workbench/agents/single/prompts/p006.txt": "4042baa661872176d3bed0a4f9014d3556b06466bd4461fef5a0e3134d9f8ff3",
  "tests/agents/test_repair_controller.py": "59c632814424139e8197c8a10fc8629e0e76d2568ce8bea327c54763c879653d",
  "tests/agents/test_repair_stage_review.py": "62d1e71c1e2eb4e68c5ffb85f8b1d9c1fcfadacf9a5799bb0829d4d25fc0a634"
}
```
