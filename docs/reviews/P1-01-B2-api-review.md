# P1-01 B2 API 与执行所有者独立代码审计

- **审计对象**：`web_repairs/api.py`、`catalog.py`、`service.py`；`WebRepairStore.active_id` 增量；顶层 `api.py` 的路由、浏览器边界与 lifespan 增量。
- **审计版本**：B1b 基线 `a68dde0c8cfd2e82d8ef67dbcd56bd1d752f2ed0` 之上的 B2 工作树，文件摘要见末节。
- **技术栈**：Python 3.12、FastAPI、asyncio/AnyIO、SQLite、POSIX flock。
- **业务场景**：General SaaS；本机可信单用户、同状态目录。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15。
- **评审者**：独立评审 Agent `b2_api_review`；未修改生产代码，只添加独立反例。

## 1. 代码质量评估卡

- **综合质量得分**：100 / 100，仅限本报告明确范围，表示本次未发现扣分项。
- **上线评估结论**：Pass，本批 API/service 代码评审通过；不等于 B2 整体交付、真实模型验收或 B3 网页操作通过。
- **审计范围**：3 个新增生产文件共 394 行，以及 2 个已有生产文件的上述局部增量，低于 2000 行门禁。
- **未评估项**：范围内 none。旧复现/分析槽及 runner/oracle 的资源终结修复由另一份 B2 resource review 评审；真实 Docker/模型与浏览器完整运行效果不属于本批独立反例。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
DEDUCTIONS:   none, sum = 0
RAW SCORE:    100
CAP APPLIED:  none
FINAL SCORE:  100 / 100
VERDICT:      Pass for the stated API/service scope
NOT ASSESSED: none within scope
```

## 2. 生产事故风险推演

未发现需要阻断本批的已确认 P0/P1。以下可达交错已通过独立测试：

| 故障/交错 | 必须保持的结果 | 独立验证 |
|---|---|---|
| 读取 HTTP 协程取消，但 SQLite 线程还没退出 | 读槽继续占用；超出 2 个读取立即拒绝；线程退出后才释放 | `test_cancelled_reader_holds_capacity_until_sql_thread_finishes` |
| preflight 未结束时 shutdown，随后 shutdown 等待者再被取消 | 不创建 receipt；仍持 owner 到 preflight 收尾；新请求停止接收 | `test_shutdown_during_preflight_never_creates_receipt` |
| preflight 内部异常含敏感字符串 | 返回稳定 503，不输出异常；owner 可重新获取 | `test_preflight_failure_is_sanitized_and_owner_reusable` |
| 同一历史请求在配置/adapter/preflight 已不可用时重复 POST | 仍返回原任务，不再调用依赖或执行模型 | `test_duplicate_does_not_use_new_adapter_or_preflight` |
| GET/取消未知 ID | 404，无新任务、receipt 或模型请求 | `test_read_and_cancel_missing_id_do_not_admit` |
| 首个提交断连，preflight 尚未完成又用同 ID 提交 | 当前 owner 存活时拒绝第二个执行；首次完成后只读复用，模型总调用一次 | `test_duplicate_retry_after_disconnect_is_not_second_execution` |
| CLI 修复任务没有网页 receipt | 网页取消拒绝，原任务字节结构不变 | `test_cli_only_task_cannot_be_cancelled_through_web_receipt` |
| GET catalog | 不接触 Docker daemon，不执行 adapter，不做接收/恢复 | `test_catalog_does_not_connect_docker_or_execute_adapter` |

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

独立执行命令：

```sh
uv run --frozen pytest tests/test_b2_api_review.py -o addopts='--import-mode=importlib' -q
uv run --frozen ruff check tests/test_b2_api_review.py
uv run --frozen ruff format --check tests/test_b2_api_review.py
```

独立反例使用真实临时 SQLite 与 owner 锁、脚本模型和受控 preflight，不访问用户主库、真实模型或实际 Docker。复用实施测试中的夹具只用于搭建依赖；八项测试的交错与断言由评审者独立编写。结果为 **8 passed**。一次去掉项目 `--import-mode=importlib` 的单独计数命令导致测试模块导入失败；恢复项目导入模式后重跑，结果如下。测试文件的 import 排序问题已由 Ruff 修复；生产代码无本评审修补。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 路由只解析严格 DTO；执行使用 B1 已审计的一次 claim 与共享 controller |
| 2 | SOLID 与现代设计 | 0 | 配置与 adapter 可注入；不复制 Agent 执行循环 |
| 3 | 并发、异步与资源安全 | 0 | owner 独立于 HTTP 等待者；读线程由 `_owned` 等待；shutdown 保留所有者直到收尾 |
| 4 | 容错与防御性编程 | 0 | 前置错误映射为稳定代码；提交之后异常不重放，保留持久 active 供显式恢复 |
| 5 | 性能、伸缩性与计算效率 | 0 | 接收/只读各 2 个门控；JSON 4 KiB、5 秒；固定两个案例与现有任务预算 |
| 6 | 安全与数据合规 | 0 | Host/Origin、本机边界、无任意路径/命令；响应不返回 claim/令牌/异常正文 |
| 7 | 可观测性与运维友好度 | 0 | 持久 receipt 与原任务可查询；catalog 区分 busy/recovery_required；不伪造异常运行成功 |
| 8 | 类型安全与契约表达 | 0 | RepairRequest、Receipt、Admission、泛型数据库操作约束边界 |
| 9 | 可测试性与死代码 | 0 | 八项独立反例覆盖不同生命周期交错，可无外部服务执行 |
| 10 | 工程规范与一致性 | 0 | 复用既有请求体解析、错误安全映射和 no-store 响应策略 |
| 11 | 数据与事务完整性 | 0 | 202 在 B1 admit 提交和 receipt 复核后返回；同参历史先于新配置；GET 不清槽 |
| 12 | 依赖与供应链治理 | 0 | 本范围没有新增第三方依赖 |

## 5. 整改清单

none。无未关闭 P0/P1/P2；无风险豁免。

## 6. 架构防腐与长效治理建议

1. 保留独立断连、shutdown 再取消、线程收尾三项反例作为 CI 门禁；新增生命周期包装时继续运行，防止把锁寿命重新绑定到请求协程。
2. B3 继续使用既定 request_id 协议：未知提交只查询，不做自动 POST 重试；页面验收必须检查刷新后不会创造新的执行。
3. 本批通过不替代资源组合审查；B2 总门禁必须同时引用 resource review 与实现侧多进程/HTTP集成结果。

## 7. 审计声明

- 本报告只对以下生产文件快照及明确增量有效；后续生产变更需要增量复审。
- 未施加任何豁免；范围内无 suspected 发现。
- 不把确定性测试数量表述为真实模型修复成功率。

| 文件 | SHA-256 |
|---|---|
| `src/agent_workbench/web_repairs/api.py` | `acb65c0559628c482d11664645ab39075ee2dda8bb8e546b82ae70d32633292f` |
| `src/agent_workbench/web_repairs/catalog.py` | `2b86574e67dd5911a90d27efbedfc7b2ef0546cef4d49045cff15a9046e62f6a` |
| `src/agent_workbench/web_repairs/service.py` | `3346693de733355143bfd013507a2d87a1f155ece509ddd9a8d0f9ef70389467` |
| `src/agent_workbench/web_repairs/store.py` | `8189828dab97c430bbdf4a75ef8a4469ae468131af1ae48a55778b7c8de532dd` |
| `src/agent_workbench/api.py` | `ee38ca6e886f3a1899b22b57837ab04a8ddcf562d7f40d63c1086318bc30ed56` |

### 收尾增量复核：交付文档与部署边界（2026-10-15）

只读核对 `docs/38-p1-01-b2-delivery.md`、README、文档 34/35、`frontend/lib/capabilities.ts` 与 `milestones.ts`。文档 38 的接口、提交后响应、历史复用、只读查询、跨 worker 停止、shutdown 及限额描述与本范围实现一致；`artifacts/b2-http-tests.log` 为 `20 passed in 8.75s`，`artifacts/b2-combined.log` 为 `1 passed in 1.72s`。另阅读真实 TCP 双 Uvicorn worker 测试及其 test-only fixture，确认模型调用由确定性替身提供，记录没有将其计为真实模型效果。

部署声明明确：源码有新 API，但本机原后端与 0007 主库未切换；B3 接通按钮前需要显式迁移/保真核对/重启。前端 repairs 仍 `web_readonly`，更新记录只新增接口文档说明，没有把未开放的操作标为网页可用。B4/B5、W08–W12 仍由后续里程碑验收。本次不重跑全量测试；文档 38 当前 `in_review` 与最终回归待核验状态正确，只有最终证据完成后才能转 done。

上表 5 个生产文件 SHA-256 均未变化。未发现本范围新的契约遗漏或未关闭 Defect P0/P1，原 Pass 结论维持。
