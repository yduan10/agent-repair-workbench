# 企业代码质量审计报告：P1-01b B2 服务与 HTTP API

- **审计对象**：`web_analyses/service.py`、`catalog.py`、`api.py` 与顶层 `api.py` 的服务注册/关闭增量，及对应服务测试。
- **审计版本**：2026-10-14 隔离目录 `<review-workspaces>/web-analysis` 冻结五文件，SHA-256 见末尾。独立评审者 evidence_review_resume，实施者 web_analysis_service。
- **技术栈**：Python 3.12、FastAPI、asyncio、SQLite、POSIX flock、Pydantic。
- **业务场景**：General SaaS；当前可信本地单用户边界。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14，Asia/Shanghai。

## 1. 代码质量评估卡

- **综合质量得分**：100 / 100（本次审计范围，无当前未关闭发现；不代表整个产品评分）。
- **上线评估结论**：**Pass**，依赖已修订 B1 的一次性接收与持久取消检查，必须按文末版本一并集成。
- **审计范围**：五个冻结文件，低于 2000 行；顶层 API 仅审查 AnalysisService 与新 router 接入、两类 owner 共同关闭的增量。B1 存储实现不重复签收，仅验证服务调用契约。
- **未评估项**：范围内 none。真实模型、真实 Docker、浏览器真实 API 联调和主库迁移属于 B3/B4，未包含，不能由本报告推定已经完成。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — 当前范围无未关闭缺陷，集成须包含最新 B1 取消边界修订
NOT ASSESSED: none within scope
```

### 实测证据

在隔离目录执行，确认导入路径是该目录的 `src/agent_workbench`，非主项目旧代码：

```text
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/test_web_analysis_service_review.py tests/test_web_analysis_service.py -q
39 passed in 6.51s

uv run --frozen pytest -o addopts='--import-mode=importlib' tests/test_web_reproductions.py tests/test_api.py -q
52 passed in 7.61s

uv run --frozen ruff check src/agent_workbench/web_analyses/{api,catalog,service}.py src/agent_workbench/api.py tests/test_web_analysis_service.py tests/test_web_analysis_service_review.py
All checks passed!

uv run --frozen mypy --cache-dir /tmp/awb-b2-evidence-review-mypy src/agent_workbench/web_analyses/{api,catalog,service}.py src/agent_workbench/api.py
Success: no issues found in 4 source files
```

39 项包括作者 33 项 HTTP/SQLite/fake adapter 生命周期测试和本评审新增 6 项反例。另 52 项回归用于确认顶层 lifespan 增量没有破坏已有复现/API。全程仅临时库，无主库升级/写入，无外部模型调用，无 Docker 实验。

## 2. 生产事故风险推演

没有需要阻断的 P0/P1。以下实际故障路径已验证：

- **接收前丢失等待者**：在资源预检线程暂停期间取消 submit 的 HTTP 等待者；被 shield 的 owner 仍完成持久接收和单次执行，随后相同 ID 复用 200，只有一条记录。
- **跨进程 owner 暂停**：另一个真实 Python 进程取得同目录 flock，SIGSTOP 后新请求仍为 429，不创建记录；SIGCONT 后正常释放才可接收。未把进程暂停当作过期租约抢占。
- **接收后执行器异常**：run_created 抛出包含私有文本的异常，已接收记录和 active 槽保留；catalog 为 recovery_required，相同 ID 只读复用，新 ID 被拒绝，无自动重跑且响应不含异常正文。
- **取消通道断开**：持久取消查询抛错时，watch 取消模型任务一次；结束后用量保留未结算预留，不能宣称零消耗。
- **首调用取消窗口**：图已调度但进入第一次 turn 前持久写取消，最新 B1 入口检查令任务 cancelled、model_calls=0、reserved_tokens=0。此用例明确证明需要 B1 修订，不能仅依赖 50ms watch。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 依赖修订复核（不是重复审查 B1）

作者交接指出原 run_created 检查与首个图节点之间存在持久取消窗口。B1 实现者已在 `AnalysisRuntime.turn` 首部读取网页任务取消状态，在任何预算预留或模型调用前停止。本评审对这个跨批次调用边界新增 `test_persistent_cancel_after_graph_scheduled_prevents_first_model`，修订后通过。报告不接受仅合入 B2、继续使用修订前 B1 的组合。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 固定案例/意图，HTTP 无路径、URL、密钥或 shell；模型配置只由服务端提供 |
| 2 | SOLID 与现代设计 | 0 | request/账本/配置/owner/runtime 分层，构造注入仅 Python 测试缝隙 |
| 3 | 并发、异步与资源安全 | 0 | 持锁 owner 跨 HTTP 生命期，shield 接收，单次取消后等回收；独立进程暂停反例通过 |
| 4 | 容错与防御性编程 | 0 | 丢响应不重投、未知状态保槽、关闭停止接收、预检失败零记录/零模型 |
| 5 | 性能、伸缩性与计算效率 | 0 | 本地单网页分析槽，模型/工具既有时间预算；非多租户吞吐承诺 |
| 6 | 安全与数据合规 | 0 | loopback、精确 Origin、JSON/4KiB/5秒；静态错误，不回显凭据/URL/异常正文 |
| 7 | 可观测性与运维友好度 | 0 | busy 与 recovery_required 分开；取消请求与最终状态分开；未知预留保留 |
| 8 | 类型安全与契约表达 | 0 | 严格 AnalysisRequest，固定 catalog 与返回码，mypy通过 |
| 9 | 可测试性与死代码 | 0 | 临时真 SQLite、HTTP、fake模型、进程锁/信号及故障注入均明示范围 |
| 10 | 工程规范与一致性 | 0 | 复用既有 HTTP 读体边界和运行记录；无自动迁移/初始化 |
| 11 | 数据与事务完整性 | 0 | 调用B1原子接收、一次性claim；重复查询先于模型配置；墓碑410；release_safe守门 |
| 12 | 依赖与供应链治理 | 不适用新增依赖 | 本批没有新增依赖/锁文件修改；不宣称重审全部依赖漏洞 |

## 5. 整改清单

none。无风险豁免。交付前集成门禁：同时合入最新 B1 runtime 修订并重跑临时库验证，不能拿冻结五文件的 Pass 替代整个 P1-01b 完成证明。

## 6. 架构防腐与长效治理建议

1. 保留丢响应、持锁暂停、接收后异常这三类反例；未来调整任务调度器时，必须继续证明“接收已持久化”和“实际执行权”分离，不能用 HTTP 是否完成作为执行凭证。
2. 保留首次调用前取消与 in-flight 未知用量两条测试；它们分别约束未发出请求与已发送请求，不能统一返回“已取消且零费用”。
3. 网页真实联调按 B3/B4独立记录模型和容器证据，维护 mock/真实两类统计，避免把生命周期测试误当模型效果验证。

## 7. 审计声明

仅审以上 B2 文件及 B1 的必要调用边界。未改生产源码、未读/写模型密钥、未运行主库迁移、未调用外网模型。新增独立测试已复制到主项目 `tests/test_web_analysis_service_review.py`，SHA-256 `7b2378f5caf691c02e2c8ba5d8561d08ed27677812589f7039719ec921bba767`。

| 文件 | 冻结 SHA-256 |
|---|---|
| src/agent_workbench/web_analyses/catalog.py | f4d7c5040bfc34e6d129e15c220aac74d3a7fdadb30235f9a055a6427488d3c7 |
| src/agent_workbench/web_analyses/service.py | 95ffbcb527edd1b5b080be8ec4d9829c96f11befe1838cac005739935c031c58 |
| src/agent_workbench/web_analyses/api.py | bdfc2711415af2d36156fd8a16c81dddf7134bcf49ea097544e828449cadc1f3 |
| src/agent_workbench/api.py | 94e92cde64ae914189545406f6efd96eb1229777eaf3bd3a7b0125ecf4babe95 |
| tests/test_web_analysis_service.py | 608391f90e0ee4a0d25b7355db39629e884a3b4c0b2c3a5e78c24261daf23686 |

必要 B1 依赖：`orchestration/runtime.py` SHA-256 `2e0aebadf7d64665a1f1d3116dae13b9ee34592a9cb07e13c5f16ddd30942894`。其余 B1 账本和迁移以 B1 独立报告为准。之后变更需对应增量复审。
