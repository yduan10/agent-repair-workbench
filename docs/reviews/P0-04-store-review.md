# 企业代码质量审计：P0-04 store

- **对象**：run_store/store,models,schema,__init__,migrations；两个store测试文件；pyproject/uv.lock；逐批范围见 SHA-256 清单。
- **版本**：2026-10-13 独立副本；`P0-04-store-snapshot.json`。
- **目录**：`<review-workspaces>/p0-04-review`。
- **技术栈**：Python 3.12.13、SQLAlchemy 2.0.54、Alembic 1.20.0、SQLite WAL、AnyIO/FastAPI、受控 Docker runner。
- **场景/严苛度**：General SaaS / Mission-Critical。按 auditing-enterprise-code-quality skill；只读实现，未构建镜像/清理容器。

## 1. 代码质量评估卡

**100 / 100；本批已审代码无已确认未闭缺陷。** 最终 P0-04 完成还需合并各批门禁，不能由本报告推导全产品生产可用。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped Pass for reviewed local code; milestone closure requires remaining cross-batch gates
NOT ASSESSED: UI/协调另批；完整UI和跨批里程碑结论由root汇总
```

独立执行：

```text
uv run --frozen pytest tests/test_run_persistence.py tests/test_run_store.py tests/test_run_store_concurrency.py -q
.....................................................                    [100%]
uv run --frozen pytest review/tests/test_p004_independent.py -q
....                                                                     [100%]
uv run --frozen ruff check src/agent_workbench/run_store src/agent_workbench/runner tests/test_run_persistence.py tests/test_run_store.py tests/test_run_store_concurrency.py
All checks passed!
uv run --frozen mypy src/agent_workbench/run_store src/agent_workbench/runner
Success: no issues found in 16 source files
uv lock --check
Resolved 55 packages in 5ms
```

共 53 项仓库测试 + 4 项独立附录反例。最初误填不存在的 `test_run_store_adversarial.py` 命令退出4，未计作测试证据；随后使用上述实际文件完成验证。

## 2. 事故风险推演

无确认 P0/P1。已追踪以下关键故障路径：

- 两个spawn进程同时claim：只出现一个claimed，另一个version_conflict，attempt和claimed事件各一份；三进程并发初始化接受成功或固定store_busy。
- late token/version/attempt/lease：finish拒绝且不留artifact；重复event ID相同内容幂等、不同内容冲突；claim不可重领。
- SQLite触发器、延迟外键COMMIT失败、SQLITE_FULL：run/attempt/event/artifact全部回滚。读事务显式BEGIN，写事务BEGIN IMMEDIATE，无持锁跨Docker等待。
- 两个读者持snapshot时第三方prune：读者仍获完整报告，后续新读取not_found；不会读半份。prune排除running/queued/未确认资源和无报告unknown。
- 空库迁移往返、含数据降级拒绝、未知revision拒绝；真实WAL backup API产生可恢复一致副本，主库后续写入不会混入备份。

## 3. 详细审计明细

### P0

none。

### P1

none。

### P2

none。设计预审 D01/D02 已由规格第6节及第3节精确 prune 规则关闭，未将文档初稿缺口算成实现故障。

### P3

none。

## 4. 维度覆盖声明

| # | 维度 | 发现 | 证据/边界 |
|---|---|---|---|
| 1 | 架构边界 | 0 | 执行协调、持久化、HTTP只读分层；不新增调度平台 |
| 2 | SOLID | 0 | 统一状态转换/报告保存；角色实现未提前混入 |
| 3 | 并发资源 | 0 | 真实多进程唯一claim、CAS、短事务、busy有界 |
| 4 | 容错 | 0 | 执行前保存失败不启动，finish失败不重跑，不假成功 |
| 5 | 性能 | 0 | 列表/事件100、报告1MiB；本机规模，大库压测不在范围 |
| 6 | 安全合规 | 0 | DTO不含token、输入原值；固定错误码、Origin/Host/no-store |
| 7 | 可观测性 | 0 | 状态事件version、report hash、record/attempt分离 |
| 8 | 类型契约 | 0 | Pydantic固定状态；mypy16文件无问题 |
| 9 | 可测试性 | 0 | 真实SQLite故障、snapshot竞争、额外反例通过 |
| 10 | 工程规范 | 0 | frozen安装、分批快照、Ruff；最终台账由root汇总 |
| 11 | 数据完整性 | 0 | terminal/report/event同事务；提交失败回滚，读回重验hash |
| 12 | 依赖治理 | 0 | 锁内版本已核对；SQLAlchemy/Alembic/Mako/MarkupSafe版本及许可证实测匹配docs06；原始扫描51项/0已知漏洞已核对 |


## 5. 整改清单

无本批未闭实现缺陷，无风险豁免。里程碑完成需 root 汇总独立 UI 评审、实际 Docker 证据、全量回归及依赖/台账更新。

## 6. 长效治理建议

1. 保留 claim/finish/提交故障反例，不允许用重试掩盖未知副作用；新增心跳或多 attempt 前另写状态契约。
2. 保留真实 SQLite snapshot/prune、多进程抢占和 WAL backup 恢复验证；替换数据库驱动时重新验证事务行为。
3. 独立附录四项覆盖取消前/后、live/mismatch 只读对账；合入正式 tests 时保留合成执行说明，不能计入真实 Docker 数量。

## 7. 审计声明

仅对快照清单的代码与本地可信单用户边界生效。未评估：UI/协调另批；完整UI和跨批里程碑结论由root汇总。本轮没有再次启动真实 Docker；父任务报告的 340 passed（含21真实Docker、1公开案例）为实现方证据，不冒称本 reviewer 实测。真实 Docker 新增测试源码已逐项阅读：独立进程读回报告、响应丢失unknown、SIGKILL后重启只读对账且不重投；UI由另一专职 reviewer 负责。首次公网/包发布、恶意本机篡改、多租户、大库压测均不属于本批范围。

## 最终依赖与文档增量复核

已复制并审阅主目录最新 docs01/02/03/04/06、README。台账P0-04保持in_review，ADR-011与docs14小报告同库原子提交一致。独立读取已安装metadata：SQLAlchemy2.0.54 MIT、Alembic1.20.0 MIT、Mako1.4.3 MIT、MarkupSafe3.0.4 BSD-3-Clause，与锁/清单一致。实现方 `artifacts/dependency-audit-p004.json` 原始JSON核对为51个条目、50项公告查询、0漏洞，仅本地agent-workbench跳过；文件SHA256 `1f176fb39d4f0e29fbe302f04a0ace97c1e8644cb552cdc3be0d8d707cb77038`。本review没有重复联网扫描；不将公告扫描扩展为未知漏洞或构建环境保证。当前批次代码/文档门禁Pass、无未闭缺陷；尚未完成的UI独立评审不在本批范围，不据此宣称整个P0-04完成。

独立附录已整合 `tests/test_run_independent.py`；AST比较确认仅删除unused Report import，逻辑一致，默认测试路径另跑4项通过。附录与正式测试为同4项，不能重复计数。快照已覆盖正式路径及最新docs。
