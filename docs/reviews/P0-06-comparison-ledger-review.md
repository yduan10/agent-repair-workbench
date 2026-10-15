# P0-06 B1c 比较账本独立代码评审

- 范围：`repair_store/{models,store,comparison_models,comparisons}.py`、`run_store/{schema,store}.py`、`migrations/versions/v0005.py`、`tests/test_repair_store.py` 的版本断言增量、`tests/test_repair_comparisons.py`；相对 B1b 约 1157 行新增，9 个冻结文件。
- 独立追加：`tests/test_repair_comparisons_review.py`，4 个反例。
- 技术栈：Python 3.12、Pydantic、SQLite / SQLAlchemy / Alembic、既有 POSIX owner fence。
- 评审者：final_review，独立于实现者 code_review_m0；日期 2026-10-14。
- 方法：auditing-enterprise-code-quality；General SaaS / Mission-Critical。在隔离开发副本检查，未迁移主数据库、未改生产实现。

## 1. 代码质量评估卡

**Pass，100/100，仅 B1c 比较持久化增量。** 没有确认的 Defect P0/P1/P2/P3。T07 入场、逐槽保存、宿主派生最终报告与未知对账可进入后续集成。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B1c comparison ledger only)
NOT ASSESSED: T05/0006 shared identities, real executor integration, HTTP/UI/model loop
```

本批 T07 的四身份在 T07 表全局唯一；跨 T05/T07 的共享唯一性属于已排定 0006 迁移，尚未实现，不计为本批已通过。比较器自身及真实 Docker 行为由其他分批评审承担；此批使用明确标注的合成 oracle 报告，不冒充真实执行证据。

## 2. 生产事故风险推演

无待修 P0/P1。核验的失败窗口：

- 入场登记中途失败：请求、工具额度、比较记录和四个容器身份在同一事务回滚，不残留半份执行授权。
- 某个槽位保存失败：结果前缀、attempt 状态和事件一起回滚，调用者必须停止执行循环；不能跳过失败继续下一个槽位。
- 四结果已有、最终提交前崩溃：显式对账仍为 outcome_unknown，保留四结果和身份，不自行补判 verified 或重跑。
- 文件或镜像版本改变：历史报告仍可读取；当前完整性核验拒绝提供沿用旧版本的 verified 结果。

## 3. 详细审计与实证

**Defect P0/P1/P2/P3：none。**

1. 只有 verification / single 对应模式能申请 T07；预算与基线/候选归属、CAS、期限、请求摘要在授权前检查。仅初次响应有私有 claim；同参重放只读，异参拒绝，同一候选不能另开比较规避限制。
2. 四个固定顺序身份先持久登记；每个槽位校验 attempt、快照、scenario、suite、oracle 与镜像绑定。只能追加连续前缀；重复同值保存不增加修订或授权，冲突值拒绝。
3. SlotResult 入口 JSON 重验嵌套 OracleReport，防止 Pydantic 对象验证后变异绕过不变量。最终结论从数据库中已经保存的报告派生，不接受外部 verdict。
4. verified 只通过内部最终状态路径写入；通用 finish_task 明确拒绝 candidate_verified。拒绝候选可返回 ready，缺项/未知/取消不能继续授权。
5. 基础读取同时复核比较记录、事件槽数、四个身份及报告摘要、任务终态关联。历史读取与 `read_verified_comparison` 当前版本核验分开，未来 API 必须保留这一区分。
6. 恢复持有原任务 owner fence；通用恢复拒绝比较任务，专用恢复仅保存 unknown。0005 只新增两表，旧表字节保真，旧 schema 只读拒绝且仅显式迁移。

### 独立执行结果

先核对 `artifacts/b1c-sha256.json` 九文件全部匹配，再读取 B1b 差分及直接调用方。最终命令：

```sh
uv run --frozen pytest tests/test_repair_comparisons.py tests/test_repair_comparisons_review.py tests/test_repair_store.py tests/test_analysis_store.py tests/test_run_store.py tests/test_run_store_concurrency.py -o addopts='--import-mode=importlib' -q
```

```text
133 passed in 9.59s
All checks passed!
10 files already formatted
Success: no issues found in 9 source files
```

Ruff / format 覆盖九文件及独立反例；mypy 覆盖 repair_store 及本批 run_store 增量共 9 个源码文件。133 项含作者 129 项和评审者 4 项。全部数据库与快照为测试独占临时内容，镜像 manifest 及 oracle 报告是标注清楚的元数据 fixture；本次没有 Docker 或模型调用。

新增独立反例：

- 插入事件失败导致四个 admitted 身份和 T07 预算完全回滚；故障撤除后仅授予一次新 claim。
- 最终提交事件失败时，task/request/report 均保持比较中；再次结算只派生一次 verified，不增加工具次数。
- 嵌套报告在构造后清空必需 steps，保存前被 `invalid_repair_input` 拒绝，前缀和修订不变。
- 第二个任务复用第一个任务的一个 T07 attempt_id，申请被拒，第二任务预算和比较表不变。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 范围内结论 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 持久比较与模型建议分离；外部无 verdict 写入 |
| 2 | SOLID 与设计 | 0 | 单独比较模型/存储，复用核心账本 |
| 3 | 并发与资源 | 0 | owner fence、事务 CAS、T07 唯一身份 |
| 4 | 容错 | 0 | 逐槽前缀、回滚、未知保留、不恢复执行 |
| 5 | 性能与限额 | 0 | 最多两份比较、每份四结果、32 KiB 记录限制 |
| 6 | 安全与合规 | 0 | 不持久 claim 明文或原始工具结果；不执行候选 |
| 7 | 可观测性 | 0 | 槽位与身份状态、版本摘要、历史/当前完整性分离 |
| 8 | 类型与契约 | 0 | 嵌套报告重验、严格顺序及版本绑定 |
| 9 | 可测试性 | 0 | 真实 SQLite/文件系统故障与合成报告明确分离 |
| 10 | 工程规范 | 0 | 九文件冻结差分，独立门禁，分批范围准确 |
| 11 | 数据与事务 | 0 | 四身份与额度原子入场，0005 保留旧行 |
| 12 | 依赖治理 | 0 | 无新增外部依赖；复用锁定栈 |

## 5. 整改清单

none；没有豁免或未关闭范围内阻断项。0006 跨表身份、真实执行集成与 UI 是后续开发范围，不把它们记为本批已经完成。

## 6. 架构防腐与长效治理建议

1. 实际 compare 回调必须在 save_slot 成功后更新 CAS 游标，再允许下一槽执行；持久化异常直接停止，禁止捕获后继续或恢复重跑。该交接需要整合后的真实执行验收。
2. API 区分历史 outcome 与 current_integrity；展示 verified 标签或下载 diff 前使用当前快照/版本核验。不能把本批只读历史接口直接当当前成功证明。

## 7. 审计声明与冻结

评审者只追加测试与报告。没有运行主库迁移、覆盖 main 实现、启停服务或发布。比较器在沙盒中的执行预算配置不是本批评审对象；主分支整合时必须保留另批已经评审的比较器版本，不用沙盒旧副本覆盖。

```text
d5e9e729cf1a767059c09731d61ab60a9199bef64cae23a486683906d4acb631  src/agent_workbench/repair_store/models.py
76feb5faa35f84e25c3809b92e786082355708e3e84b70750f1e039324ee39f3  src/agent_workbench/repair_store/store.py
4da6a621779e52dd1a54de6d2bcdee43779ecc912583c191cbea359d41695ef3  src/agent_workbench/repair_store/comparison_models.py
e0039d0f4a194e1bde03e4eed7a29b77daacc87ad06e61ddc2c580fb874e92cc  src/agent_workbench/repair_store/comparisons.py
388c3b277a1b1b9f490748dad0435cf008c6a223e5dcdd962fc869a72cb3e99d  src/agent_workbench/run_store/schema.py
9bcc19f39038567dca6781389ec80ed1da74c01974019d1a9285ba80aecb47ea  src/agent_workbench/run_store/store.py
6be58936c78ff66b8e6bdfcd74b6cce0fb59c2e985283918c0abc480ffb5820e  src/agent_workbench/run_store/migrations/versions/v0005.py
5971a33c34492d95e7d59e6864db7e834aecd30d0631364c16b559c5d273f7f5  tests/test_repair_store.py
ef223db0755107d42db4ff75b3e166b4662c33fe32634a54f45d05dc1f55532d  tests/test_repair_comparisons.py
2fbe292dd245de1d1e63e82f66dcbae7e1d1cd436bbdc8efbe7bc0d72ff61979  tests/test_repair_comparisons_review.py
```
