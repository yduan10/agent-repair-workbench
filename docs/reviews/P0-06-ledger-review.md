# P0-06 B1b 核心修复账本独立代码评审

- 对象：`repair_store/{__init__,models,fencing,store}.py`，`orchestration/budget.py` 的纯委托提取，`run_store/{schema,store}.py` 的 0004 增量，`run_store/migrations/versions/v0004.py`，`tests/test_repair_store.py`。
- 追加：`tests/test_repair_store_review.py`，4 个独立反例。
- 技术栈：Python 3.12、Pydantic、SQLAlchemy / SQLite、Alembic、POSIX flock。
- 方法：auditing-enterprise-code-quality；General SaaS / Mission-Critical。
- 日期：2026-10-14；final_review 独立于实现者 code_review_m0。生产实现只读，快照见文末。

## 1. 代码质量评估卡

**Pass，100/100，仅核心账本批次。** 没有确认的 Defect P0/P1/P2/P3。当前只保存模型/工具/候选申请与结算元数据；比较记录、T07 容器身份、实际执行、公开 API、CLI 与网页整合尚未包含在本批。不得凭本结论宣称完整 P0-06 可用。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B1b core repair ledger only)
NOT ASSESSED: comparison/execution identities and user-facing integration; later batches
```

## 2. 生产事故风险推演

无待修 P0/P1。承重场景及结果：

- 相同请求并发/重发：同参数只读返回旧记录，不再返回 claim；异参数、角色或操作冲突拒绝，不能重复授予执行权。
- 预留或结算事务失败：预算、请求、候选序号和事件一起回滚；已持久的旧预留保留，结算可在同一 claim 下重试一次，不能重复计账。
- 快照已发布但候选记录未提交：恢复保存 outcome_unknown，不自动重复应用、不删除已发布快照；候选次数和工具额度不重置。
- owner 被 SIGSTOP：另一个进程不能抢占恢复；SIGKILL 后锁释放，显式对账终结为 unknown，旧 claim 不得继续结算。

上述文件系统/数据库窗口不是跨系统 exactly-once 保证。本库提供持久授权与失败保留，实际执行器仍必须遵守“先登记后执行”。

## 3. 详细审计明细与实证

**Defect P0/P1/P2/P3：none。**

1. 严格校验 task / patch / snapshot DTO，公开元数据不含 claim 原文、模型输入/输出正文或磁盘路径。预算、候选次数与角色权限同一任务累计；三个角色不能分别获得新额度。
2. `RepairFence` 绑定目录、任务和 PID；持久写入需 owner，事务使用既有 BEGIN IMMEDIATE 和版本/摘要 CAS。请求幂等检查在授予新 claim 前完成，终态重放不返回授权。
3. 读取时验证行摘要与规范编码，重建不可变请求事件序列、用量、候选序号及状态关联，而非直接信任累计计数。未知模型用量保留原预留，并终结当前任务。
4. 0004 只新增四张表；旧 AnalysisSummary/Event 含义未改。只读访问不会偷偷升级 0003，显式 initialize 才迁移；降级检查有数据时拒绝。
5. 纯 `reserve_usage` 提取保持旧 `reserve(summary, request)` 委托入口，未改变原预算计算逻辑。没有新增外部调用或依赖。
6. 基线和候选 DTO 只是已经核验的元数据。调用层必须先经 SnapshotStore 核验真实文件，再交给本库；本库存储提交不等于候选执行或修复通过。

### 独立门禁

仅使用测试临时 SQLite / 快照目录。没有迁移主数据库、没有重启 API、没有执行模型或候选程序。

```sh
uv run --frozen pytest tests/test_repair_store.py tests/test_repair_store_review.py tests/test_run_store.py tests/test_run_store_concurrency.py tests/test_analysis_store.py tests/test_reviewer_analysis_store.py -o addopts='--import-mode=importlib' -q
```

```text
102 passed in 6.50s
All checks passed!
10 files already formatted
Success: no issues found in 8 source files
```

Ruff / format 覆盖本批 8 个源码文件与 2 个测试文件，mypy 覆盖本批 8 个源码文件。102 项包括核心账本、既有运行/分析/并发回归及 4 项新增独立用例；不计为实际模型或容器验收。

独立新增反例：

- diagnosis / repair / verification 交替结算 12 次后，任一角色第 13 次均被预算拒绝。
- 结算时注入 SQLite event trigger 失败，旧预留及 claim 保留；移除故障后准确结算一次，重复结算拒绝。
- 实际生成候选快照后模拟元数据未提交的中断，恢复 unknown 且保留快照，再次同请求不返回新 claim。
- 相同 request_id 改角色或把 model 操作改为 tool，均拒绝且账本不变。

迁移测试实际备份临时 SQLite 后从 0003 升 0004，对照旧八张表所有行；run/report、analysis 和 web 请求有已写入记录，迁移后保持原值。初次评审为显示计数曾清空 pytest addopts，意外取消仓库 importlib 模式引发收集失败；确认是评审命令错误，已撤回缺陷判断。最终命令保留项目所需 import 模式。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 证据 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 新 repair 账本与旧 analysis 生命周期分离 |
| 2 | SOLID 与设计 | 0 | 契约、锁、事务分层；预算纯函数复用 |
| 3 | 并发与资源 | 0 | OS owner、事务 CAS、真实暂停/死亡进程测试 |
| 4 | 容错 | 0 | 原子回滚、unknown 保留、晚到 claim 拒绝 |
| 5 | 性能与限额 | 0 | 请求 32、候选 2、事件/负载有界；读重建有上限 |
| 6 | 安全与合规 | 0 | token 仅哈希、无模型正文、无执行接口 |
| 7 | 可观测性 | 0 | 单调修订事件、失败码、未知用量与来源元数据 |
| 8 | 类型与契约 | 0 | 严格 DTO、入口再校验、mypy 通过 |
| 9 | 可测试性 | 0 | SQLite 故障、并发、迁移和独立反例实跑 |
| 10 | 工程规范 | 0 | 独立分批冻结、状态边界明确、无主库修改 |
| 11 | 数据与事务 | 0 | 预算/请求/序号/事件同事务，FS 与 DB 分开 |
| 12 | 依赖治理 | 0 | 无新包，沿用锁文件与既有数据库栈 |

## 5. 整改清单

none；无豁免。测试文件的跨文件 helper import 由作者局部整理为本地合成 helper，最终版本已复核并纳入上述门禁；不是生产缺陷修复。

## 6. 架构防腐与长效治理建议

1. 后续 T06/T07 适配层只允许持有本次返回的非空 claim 执行副作用；只读重复返回不能触发重新调用。必须新增真实崩溃窗口验收，不以纯账本测试代替执行幂等。
2. 比较/执行身份扩展保持同任务预算与 owner fence；旧 source_analysis_id 仅作来源，不恢复旧终态预算或导入短暂模型片段。

## 7. 审计声明

该结论适用于下面冻结版本的 B1b 核心账本，不覆盖尚未冻结的比较持久化、实际文件接通和网页。没有声称完整修复能力、真实模型修复率或主库升级已完成。任何修改后需按影响范围增量复审。

```text
db9f69514358d8b065416edc6820463ec46be72c104fda2e9a5331b161c78ccd  src/agent_workbench/repair_store/__init__.py
e6581dae7ff8133c7c4d754485531e7cfcb26b838d84194971b4b4eaf5a780f7  src/agent_workbench/repair_store/models.py
19fdae3e5443b8309f7f4e42634a73a70e820053ec2e6fb0e1d4ba4227db681c  src/agent_workbench/repair_store/fencing.py
9a01dc2d23e6a6db9676ccb50c7166c4f860841f14fa32945948a2d535865b28  src/agent_workbench/repair_store/store.py
52fe6719e38e3911768ced8b2eded0a73eda8c60beea33bdfda26ef13ef43175  src/agent_workbench/orchestration/budget.py
01fd7b4f414415e7dca85f6e4aa50a22eae4ece42539819718510cc4fd0e6d9e  src/agent_workbench/run_store/schema.py
cfcabdb923ac4d3e3c4b9376ef7517e2afcc934c742299a0c4e99f0230ad50d2  src/agent_workbench/run_store/store.py
88f319b24d22db59c61cef3aecd75390aa53eae1156f78d44e0df34eb3e36ca0  src/agent_workbench/run_store/migrations/versions/v0004.py
559aa8759af51eff5a101f2dec301a9c5f0767e8d868c0389ca2f41d89bb90cb  tests/test_repair_store.py
8a55e1c71bac8d6aa62293c3a93cff0fc20716889b60fffbfb75c2c5b1e7be50  tests/test_repair_store_review.py
```
