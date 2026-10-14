# P0-05b B1 分析存储独立代码评审

- 日期：2026-10-14；依据 docs24、角色契约与现有运行存储。
- 范围：analysis_store 六文件、run_store/schema 与 store 相对 879bf6a 增量、0003 迁移、API 路由接入、29 项作者测试与 2 项独立探针。实现/差分约 1500 行，冻结文件见 `P0-05b-store-snapshot.sha256`。
- 主审未参与 B1 实现；只读复制冻结源码至独立评审目录，仅新增测试/报告。
- 方法：auditing-enterprise-code-quality；General SaaS；Mission-Critical。

## 1. 代码质量评估卡

**Pass，仅 B1 存储、迁移与只读 API 范围。** 无未关闭 Defect P0/P1/P2/P3。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B1 only)
```

模型实际发送、工具资源注册、真实 Docker T05 和图协调不属于 B1，不由此次结果宣布完成。这里证明事务授权与持久状态边界；调用者仍须只在 reused=false / created=true 且持有 claim 时执行真实副作用。

## 2. 生产事故风险推演

未发现残余阻断。以下风险由实际测试验证：

- owner 暂停后另一个协调器接管会造成并行执行：独立进程 SIGSTOP 后恢复被 analysis_busy 拒绝；SIGKILL 后才能恢复，且仅 outcome_unknown，原预留不退还。
- 预留摘要写入但 claim 失败会产生半条任务：作者真实 SQLite 事务测试确认摘要、事件、run 和绑定一起回滚。
- 故障后重复请求再次获取发送许可：同摘要/事件版本返回 reused；异事件冲突；T05 重复请求返回旧记录、claim=None。
- 升级破坏既有报告：独立 0002→0003 测试逐行比对 runs/attempts/events/artifacts/web_requests，报告模型亦一致；非空降级拒绝。

## 3. 详细审计明细

无确认缺陷或待判 suspected 项。

### 已核对的承重契约

1. `analysis_store/store.py` create/save 对 model_copy/model_construct 后对象重新经 JSON 严格验证，限制摘要 256KiB、事件 16KiB、revision 0..255；保存摘要和事件在同一 BEGIN IMMEDIATE 内。最终版本检查 CAS UPDATE.rowcount==1，不能只插入事件却未更新摘要。
2. `analysis_store/validation.py` 校验不可变字段、合法状态转移、事件引用子集、计数变化；模型发起绑定唯一 call_id、request 与 reservation 摘要。结算必须匹配唯一未终结发起事件，输入/输出分别不越预留；unknown 不退还额度并阻止再次模型预留。
3. 幂等只复用完全相同摘要与最后事件，返回 reused=true；同摘要不同事件/调用标识冲突。终态不接受新版本写入。
4. `reserve_execution` 在同一事务中更新摘要/事件、创建 run、claim、保存任务关联；重复 task/request 不授新 claim，payload/config/case 不匹配拒绝。绑定 run 不被原 prune 删除；报告读取验证任务归属。
5. `AnalysisFence` 非阻塞 flock、UUID 文件名、拒绝 symlink、普通文件、CLOEXEC；reconcile 必须取得同锁，不能恢复存活或暂停 owner，死后不重发任务。
6. 读取使用显式 SQLite 快照事务；校验摘要与事件原始 SHA、严格 schema/canonical、事件连续版本、账本数值与执行链接。错误转安全固定码。
7. 0003 只增加新表/约束，0001/0002 需显式 initialize 升级；当前读接口不偷偷迁移。downgrade_empty 检查新增表，非空拒绝。无库 list=[] / detail404，不创建目录和库。
8. `/api/analyses` 仅 GET、limit 1..50、UUID 严格、复用精确 Host/Origin/no-store；无模型凭据读取，无执行入口。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | 分析摘要/事件与既有 run 关联，未复制执行器 |
| 2 | SOLID | 状态校验、事件 DTO、fence、事务、API 分离 |
| 3 | 并发与资源 | 非阻塞任务 owner 锁、CAS、显式事务；真实进程验证 |
| 4 | 容错 | 失败回滚、unknown 不退款、终态保护、固定错误码 |
| 5 | 性能与限额 | 事件/摘要/版本/list 有明确上限；本机 SQLite 范围 |
| 6 | 安全与合规 | 严格安全事件无自由文本，任务关联校验，无模型调用 |
| 7 | 可观测性 | 固定角色/原因/引用与账本事件可追溯 |
| 8 | 类型与契约 | 严格 DTO、写前二次验证、读取哈希/schema 校验 |
| 9 | 可测试性 | 原有、故障注入、独立进程/迁移测试通过 |
| 10 | 工程规范 | 分批审查、冻结 SHA、Ruff/mypy 通过 |
| 11 | 数据与事务 | 摘要/事件/claim/绑定原子；完整旧数据迁移保真 |
| 12 | 依赖治理 | 复用锁定 SQLAlchemy/Alembic，无本批新依赖 |

## 5. 整改清单

无待修项、无风险豁免。作者在冻结期间追加 CAS rowcount 防护及 RAISE(IGNORE) 回归，已纳入最终源码与独立执行；该项不冒称为评审者首次发现。

## 6. 架构防腐与长效治理建议

1. 将独立 SIGSTOP/SIGKILL 和完整五表迁移探针纳默认门禁；它们覆盖单进程锁测试和只保留 tombstone 测试的盲区。
2. 后续 B3 必须消费 reused/created 结果：返回旧状态不等于重新获取模型发送或 Docker 执行许可。
3. 后续真实模型阶段明确区分未知 usage、已知计数与提案未执行状态；安全事件不要增加原始模型文本兜底字段。

## 7. 审计声明

独立副本运行，未操作生产 DB、未调用模型、未启动 Docker、未修改实现。实际命令与输出：

```text
python -m pytest -o addopts='' -q tests/test_analysis_store.py tests/test_reviewer_analysis_store.py tests/test_run_store.py tests/test_run_store_concurrency.py
66 passed in 5.06s
ruff check src/agent_workbench/analysis_store src/agent_workbench/run_store/schema.py src/agent_workbench/run_store/store.py src/agent_workbench/run_store/migrations/versions/v0003.py src/agent_workbench/api.py tests/test_analysis_store.py tests/test_reviewer_analysis_store.py
All checks passed!
mypy --no-incremental src/agent_workbench/analysis_store src/agent_workbench/run_store/store.py src/agent_workbench/run_store/schema.py src/agent_workbench/api.py
Success: no issues found in 9 source files
```

共 29 项作者 B1 测试、2 项独立探针和 35 项旧存储/并发测试；不将作者另一组 78 项重复加总。初次试图在无 Git 的作者副本运行 diff 失败，随后使用主仓只读 git show 879bf6a 与副本作文本差分，不涉及代码或数据失败。范围内无未评估实质代码；完整运行时/A14/A15 仍由后续批次单独验收。


## 8. B1 运行对账增量独立复审（2026-10-14）

第二位独立评审者 final_review 复核 `run_store/execution.py` 新增的关联分析锁，并核对主仓已同步的作者与原评审反例。范围为此文件约 25 行增量及对应测试，不重复宣布全运行时通过。

**结论：Pass；100 − 0 = 100，无封顶、无豁免、无未关闭缺陷。**

- 从分析执行关联表查询 task_id 后、任何容器 inspect 或状态对账前，取得同一 `AnalysisFence`；存活或 SIGSTOP owner 返回 analysis_busy 并跳过，finally 关闭所有已取得锁。
- 锁持续覆盖 inspect 与 CAS reconcile。owner 死亡释放内核锁后，只对既有 run 标记未知；不重新执行，不修改分析预留账本。不存在先检查 owner 后无锁更新的窗口。
- SIGSTOP 真进程反例确认过期 lease 仍不 inspect；SIGKILL 后允许只读 inspect 并记 outcome_unknown。五张旧表迁移保真与预留账本不变仍通过。
- 十二维度覆盖沿用第 4 节；本次额外核对并发/容错/数据事务与资源关闭；无新增依赖、端点或对外数据字段。部署范围仍为可信单用户 POSIX 本地环境。

实际主仓命令及结果：

```text
uv run --frozen pytest -o addopts='--import-mode=importlib' -q tests/test_analysis_store.py tests/test_reviewer_analysis_store.py tests/test_run_store.py tests/test_run_store_concurrency.py
67 passed in 6.49s
uv run --frozen ruff check src/agent_workbench/run_store/execution.py tests/test_analysis_store.py tests/test_reviewer_analysis_store.py
All checks passed!
```

冻结 SHA-256：

```text
3fd2ed8546276747265032f88e2e6d2eb27fe678a40d3dad8b794e8ebbf771c1  src/agent_workbench/run_store/execution.py
6c1169c303ac1ee9835cf04475ba3c2dcd29f2a6b56169564c0c2552c84cd62d  tests/test_analysis_store.py
44c2e0add2287b2640b131727ba4ddea2fe251cc5363b2ccd8396a512d166435  tests/test_reviewer_analysis_store.py
```

此次只读实现并生成报告，未操作主数据库或调用模型。后续若上述实现变更须重新审查增量。
