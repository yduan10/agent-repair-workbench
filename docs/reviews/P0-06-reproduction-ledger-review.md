# P0-06 T05 复现账本独立代码评审

- 审计对象：T05 专用复现预留/报告/恢复、0006 共享执行身份迁移；8 个作者冻结文件，945 行新增，及4个独立反例。
- 审计版本：文末逐文件 SHA；作者 review_ui_api，独立评审 final_review。
- 技术栈：Python 3.12、Pydantic、SQLAlchemy/SQLite、Alembic。
- 场景 / 严苛度：General SaaS / Mission-Critical。
- 日期：2026-10-14。按 auditing-enterprise-code-quality 审计。

## 1. 代码质量评估卡

**Pass，100/100；可整合这批存储模块。** 无确认的 Defect P0/P1/P2/P3。范围内无未评估文件；不替代端到端修复控制器、真实执行恢复、模型实验及前端验收。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (T05 storage and migration only)
NOT ASSESSED: none within the frozen scope
```

## 2. 生产事故风险推演

无确认 P0/P1。实测高影响故障路径：结算已写报告、但事件插入失败时整笔事务回滚；旧 claim 在此失败后仍可完成一次结算，完全相同的已完成报告只读重放。身份表或必要触发器缺失/替换使读取失败关闭。中断的待执行身份保留为 unknown，不生成新 claim。

## 3. 详细审计明细

### 缺陷

P0/P1/P2/P3：none；无豁免、无待修实现。

### 独立核对的契约

- T05 请求有独立 operation 与冻结 wrong_type 基线计划；与旧泛型 T05 元数据区分。新 ReproductionStore 禁止通过普通 reserve_tool(T05) 绕过登记。
- 新请求同一 SQLite 事务持久化复现记录、全局 attempt 身份、请求、预算、任务和事件；claim 仅首次返回。同参旧请求返回历史，不受陈旧 CAS 诱导重执行；异参拒绝。
- T05/T07 插入触发器共享 attempt 主键，两个方向冲突回滚整个请求。0005 已有比较身份回填；失败升级回滚 DDL/版本；旧 task/request/event/candidate 字节与 hash 保真。
- 每次 RepairStore 读取审计新增链接、计划/请求摘要、状态与执行身份，原 ComparisonStore 读取也会检查共享身份。必要触发器按固定 SQL 核对。
- OracleReport 经 JSON 重验，校验双快照摘要、attempt、scenario、suite/oracle/image 绑定；只有完整预期 count_type 基线失败、清理确认且版本核验有效，才返回 ready。不存在 candidate_verified 路径。
- 取消、不可判定及资源未知终止任务；专用对账要求新的独占 owner，保留原身份、结为 unknown，不运行容器。读取历史报告不构成重新执行或当前候选已通过的授权。

### 实际验证

独立原测试集：`130 passed in 8.68s`。新增独立测试：

1. 结算事件插入故障回滚 report/request/task，原 claim 可重试；成功重放无 claim 且工具计数不变。
2. 嵌套可变报告的 steps 清空后拒绝持久化，原 pending 完整保留。
3. 1 次原 T06 + 19 次 T05 达到共享20工具上限，第21次入账前拒绝且数据库计数不变。
4. 同名触发器被替换为无约束 SQL 后，读取拒绝为 schema_incompatible。

最终合并运行：

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib'   tests/test_repair_reproductions.py tests/test_repair_reproductions_review.py   tests/test_repair_comparisons.py tests/test_repair_store.py tests/test_run_store.py -q
```

```text
134 passed in 9.06s
All checks passed!
9 files already formatted
Success: no issues found in 7 source files
```

后三项分别为冻结8文件+独立测试的 Ruff / format，以及7个源文件 fresh mypy。使用真实临时 SQLite 和不可变源码快照，OracleReport 与镜像 manifest 明确是合成测试材料；本批不运行 Docker 或模型，不计真实修复成功率。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 依据 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 复现账本独立，不改旧分析含义，不承担执行 |
| 2 | SOLID 与设计 | 0 | 复用 ComparisonStore / RepairStore，共享账本逻辑 |
| 3 | 并发与资源 | 0 | owner fence、事务 CAS、单次 claim、全局唯一身份 |
| 4 | 容错防御 | 0 | 入账/结算故障回滚，unknown 不重投 |
| 5 | 性能伸缩 | 0 | 任务请求数有界，身份审计查询有上限；本机单用户范围 |
| 6 | 安全合规 | 0 | 无原始参数/结果/密钥输出，无 host 候选执行 |
| 7 | 可观测运维 | 0 | 保留 attempt/事件/报告摘要，固定错误码 |
| 8 | 类型契约 | 0 | DTO 边界重验及嵌套变更反例 |
| 9 | 可测试性 | 0 | 实际 SQLite 故障注入、预算边界及迁移反例 |
| 10 | 工程规范 | 0 | Ruff / format / mypy 通过，作者/评审分离 |
| 11 | 数据事务 | 0 | 共享身份原子登记，旧记录保真，失败迁移回滚 |
| 12 | 依赖治理 | 0 | 无新增第三方依赖，frozen 环境运行 |

## 5. 整改清单

none。未提出无证据推测，也未修改实现。

## 6. 架构防腐与长效治理建议

1. 后续执行控制器只使用本账本新 claim 启动外部副作用；历史 get/replay 只读。接入时加真实宿主中断与精确 reap 门禁，成本为已有 Docker 故障测试扩展。
2. T05/T07 新增身份字段或迁移时继续保留双向冲突、旧字节保真和触发器篡改反例，防止新工具独立去重绕过共享表。

## 7. 审计声明

结论只针对以下冻结源码与直接调用边界。未迁移用户主库、未启动服务/构建前端、未调用模型，未宣称完成 P0-06。执行器的宿主死亡后残留发现/回收和完整模型预算接入属于待验收后续批次；本账本只保存/终结执行身份，不负责 inspect 或 kill 容器。代码变化需增量复审。

```text
47b2918890ce8e3aca5576d66c87d09623812def0b008c680150261e2bbcb8c7  src/agent_workbench/repair_store/reproduction_models.py
6c2aeabc55e2b4b78fa6493d337cb4ff80eb156d60dc302f14c2dad41fb2dca0  src/agent_workbench/repair_store/reproductions.py
ad0a9e8472dc1becccd6f04dff655bf80cd29763396b9d309fce98ca84ad4f76  src/agent_workbench/repair_store/models.py
198629e74a7b14958e8639b9cf410546db332c6b7483e6c7767e98354c963e0c  src/agent_workbench/repair_store/store.py
cc20f657401511143e2d441e9cf24d178e36a2bc35dcee71ba3d4f8fca19a280  src/agent_workbench/run_store/migrations/versions/v0006.py
7b3d0cd4d02a3d48a69287b0fb958a5ad9530fa068a61f66787b02bef617e720  src/agent_workbench/run_store/schema.py
04ec01b1115cfb48895e2c33696e49dbcded5b83d151306ff88c64a71f159d21  src/agent_workbench/run_store/store.py
1da81b39ffd84513fb76392f605c5bc89b11ff40deca033b30a0df9a9e8c3986  tests/test_repair_reproductions.py
620d117fca55fa1d5781ef709b389a1c0024ad9ee22646d5a9cc2060656d6503  tests/test_repair_reproductions_review.py
```
