# P0-04：运行状态、产物与恢复对账

2026-10-13 / Feature P0。前置 P0-03、UI-03 已完成。范围：可信本机运行记录，网页只读接通；不新增网页执行、模型或自动重试。

## 1. 状态与存储契约

使用 SQLAlchemy 2.0 + SQLite / Alembic，短事务、busy_timeout 1000ms、WAL、foreign_keys=ON、synchronous=FULL。每次写操作状态与事件同一事务；不持事务等待 Docker 或 LLM。

模块 `run_store/` 独立于 `runner/` 和产品角色。默认 `artifacts/run-store/state.sqlite3`，通过 `AWB_STATE_DIR` 配置独立本地目录；权限目录0700/数据库0600，错误只返回固定码。显式 `runs init` 迁移，读接口不创建库。首次 `sandbox-check` 可在执行前准备库，失败不得启动Docker。

- runs：run_id、status、version、created_at/updated_at、profile/scenario、config/case摘要、当前attempt_id、lease_until、report摘要。
- attempts：attempt_id、run_id、lease_token（不对网页输出）、开始/结束、终态。
- events：run_id、递增version/唯一event_id、固定事件类型与时间，不存用户文本。相同事件ID及同内容幂等；ID冲突不同内容拒绝。
- artifacts：run_id/attempt_id、SHA256、size、JSON报告BLOB。只存现有metadata-only SandboxReport，≤1MiB，不保存原始参数、结果或stderr。

本阶段报告小于1MiB，直接和终态一起存入SQLite使报告/索引/事件原子提交，规避文件rename与DB提交间崩溃窗口。目录存数据库及WAL；未来大体积候选文件再采用独立产物协议。本决策修订架构中泛指的产物文件存储，导出时仍可得到JSON报告并验证hash。

## 2. 执行与租约

queued → running → succeeded / failed / cancelled / outcome_unknown。每次claim分配独立attempt UUID及私有lease token，以version+status CAS领取，两个进程竞争只能一方成功。本阶段不重试、不二次执行已有run。

执行前持久化running；Docker容器run-id使用attempt_id，确保重启可精确定位。租约120s，长于当前执行30s+创建ACK/清理预算；finish必须匹配attempt/token/version且lease未过期，晚到worker不得覆盖终态。无心跳是本阶段固定短任务的明确限制；后续长任务接入前须新增续约契约。

`sandbox-check`保留原报告与退出码，并增加持久run_id引用；无法保存报告时退出2、记录存储错误（如能记录），不得显示成功。原始运行函数仍可独立使用做隔离测试，只有CLI协调层承担持久化。

## 3. 对账与保留

`runs reconcile` 显式对账过期running：先读快照，再查询Docker精确attempt名称/标签，最后以version CAS落事件。任何检查不到可靠成功报告的中断均标outcome_unknown；不根据容器退出0猜工具成功，不重投。Docker失联/存在活跃容器/未知创建均保留执行清理未确认，不自动删除活跃容器；停止且准确归属的残留可复用reap显式回收。

对账记录固定executor_state：absent / running / stopped / unavailable / mismatch。只读探测和数据库提交间变化不提供全局原子承诺；unknown是保守结果。容器独立监护继续保证本机正常调度下有限存活。

默认保留30天，可配置 `runs prune --days N`，默认dry-run，`--apply`才删除。仅终态、无未决清理风险、超过期限记录可删；queued/running/未确认执行资源的unknown不得删除。资格按终态updated_at计算；必须executor_state=absent且有SHA有效报告，报告cleanup=removed/not_created且无create_unconfirmed。无报告的崩溃恢复unknown即使一次探测absent也不自动清理。删除run/events/artifact一个事务；报告读取同一数据库snapshot，读取期间不发生文件缺失/半截内容。配置限定1～3650天，无全局目录扫描删除。

## 4. CLI与只读网页

- `runs init`、`runs list`、`runs show UUID`、`runs report UUID`、`runs reconcile`、`runs prune [--days 30] [--apply]`。报告读取时重新校验大小、SHA及schema，损坏返回固定错误。
- `/api/runs?limit=50` → `{runs:[RunView]}`；`/api/runs/{id}` → `{run:RunView,events:[EventView]}`；`/api/runs/{id}/report` → metadata-only SandboxReport JSON download。
- RunView公开字段：run_id, attempt_id|null, status, version, created_at/updated_at(Unix秒), lease_until|null, profile, scenario, config_sha256, case_sha256, report_sha256|null, executor_state|null。
- EventView字段：event_id,version,kind,created_at。无lease_token、原始参数、主机路径。
- 无库时list返回空列表；不存在404，busy/不可用503，损坏拒绝；列表上限100，详情事件上限100，全部沿用loopback/Origin/no-store限制。
- 任务总览接通真实只读列表、详情事件、报告下载与刷新/空态/错误恢复，显示真实状态而非合成任务。发起/取消/审批留P1-01，任务侧栏标“记录可用”。其他角色仍按原计划。

## 5. 验收矩阵

1. 双worker多进程抢占、版本冲突、过期token、重复事件、事务回滚：不双执行、不丢事件、不覆盖新状态。
2. 真实SQLite busy、写入失败、报告提交失败、报告hash/schema损坏：固定码、无假成功。
3. Alembic空库升级/降级/再升级；含记录降级拒绝，不能静默丢记录；未知新版schema fail closed。
4. 重启读回，真实容器成功/响应丢失持久化；宿主SIGKILL后重启对账unknown，无重投；daemon失联和迟到worker负例。
5. 默认30天dry-run/apply、正在运行和未确认资源排除；并发报告读取/删除全有或不存在；无部分产物。
6. API真实SQLite集成、坏ID/越界limit/来源限制/坏report；前端真实空库与真实测试运行列表、详情下载、断网恢复、浅深/移动/axe；mock仅用于异常边界。
7. 原284项Python和19项前端回归；独立store/协调API/UI分批review，修复复审。未实现不能标done。

官方依据：https://docs.sqlalchemy.org/en/20/dialects/sqlite.html ，https://alembic.sqlalchemy.org/en/latest/batch.html 。依赖以uv.lock和本机测试为准。

## 6. 设计预审补充

- claim只有首次CAS成功者获得执行权；重复claim返回冲突，事件幂等不能用来领取第二份执行授权。
- finish在同一写事务内取得now，并以run/version/attempt/token/lease未过期共同作为更新条件；失败回滚报告和事件。
- mapping：可靠通过且清理确认→succeeded；可靠契约失败/isError/调用前拒绝→failed；调用前取消且清理确认→cancelled；调用后无终态、契约拒判、清理未知或create_unconfirmed→outcome_unknown。报告提交失败一律CLI退出2，保留running等待对账，不把旧报告升级为成功。
- 对账可再次更新unknown的executor_state与事件，业务状态仍unknown；不会重新排队/执行。每批最多100项；live container和daemon故障不自动删除。
- 原SandboxReport.run_id继续是attempt/container UUID，新增record_id为持久运行UUID；保存时两者须与数据库一致。前端显示run_id，资源定位用attempt_id。


## 7. 本次后端验证记录

- `AWB_PUBLIC_CASE=1 AWB_DOCKER_TESTS=1 uv run --frozen pytest`：340 passed，93.84 秒，包含原284项和本轮56项（35存储、18协调/API、3真实容器恢复），无跳过。
- 独立reviewer另构造4个取消前/后与资源归属反例，已原义整合 `tests/test_run_independent.py` 并单独4 passed；当前共344项用例，其中21项真实Docker、1项公开来源案例。
- 真正SQLite事务验证包含BEGIN IMMEDIATE竞争、COMMIT失败、SQLITE_FULL、活动WAL备份/恢复与读取snapshot期间清理。
- Ruff check / format、mypy26源文件、uv lock检查通过；依赖公告扫描50项、0已知漏洞。
- 本地手动执行正常调用和响应丢失，分别退出0与2，均保存3个事件（created→claimed→finished）；新API与网页读取这两条实际容器运行记录。对应证据在忽略的 `artifacts/p004-live-evidence.json`。
- 浏览器下载正常执行报告后，磁盘文件SHA与SQLite保存摘要一致；这里的工具场景是合成fixture，实际容器与持久化执行真实，不计为用户项目接入案例。
- 独立设计复审与store/协调评审分别见 `reviews/P0-04-design-review.md`、`reviews/P0-04-store-review.md`、`reviews/P0-04-coordinator-review.md`。
- 网页门禁与最终状态见[只读记录页](15-run-history-ui.md)及台账；本段后端通过不提前代替UI评审。
