# P0-06 网页分析准入集成独立复审

- **审计对象**：`AnalysisRuntime.run_created` 新增五行固定案例门禁；展示命令测试将过时反例改为未知案例。不是完整 orchestration 审计。
- **审计版本**：HEAD `802bf70ebb509ac7e5bd7ebb8f189b4070553823` 当前工作树，文件指纹见文末。
- **技术栈**：Python 3.12、Pydantic、FastAPI、SQLite。
- **业务场景**：General SaaS，可信本机单用户。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15（Asia/Shanghai）。
- **独立性**：评审者未实现生产修复，只新增独立测试；无模型请求、Docker 或主数据库写操作。

## 1. 代码质量评估卡

**Pass，100 / 100，限本次增量。** 未发现 Defect P0/P1/P2/P3。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass — repair-only 注册表不会扩展旧网页分析执行入口
NOT ASSESSED: none within the five-line admission integration scope
```

范围之外：修复引擎、模型效果、沙箱、全站 UI 和全部 API 的完整上线认证。此分数不表示整项目无缺陷。

## 2. 生产事故风险推演

没有未修 P0/P1。本增量防止未来内部调用误把新 `counter_offset` repair 注册表用于 `run_created`，从而扩大网页分析目录。新门禁位于 `store.start_created` 之前：拒绝不消耗 claim、不推进阶段，也不将预取消任务误保存为结束。原数据库 receipt 的案例匹配仍是第二层保护。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 实现核对

- `orchestration/runtime.py:437-442`：将 registry `case_name` 绑定局部变量；只接受 `output_mismatch` / `passing`；其他值抛 `StoreError("admission_invalid")`。之后才调用持久化的一次性 claim 消耗。这不是只对类型检查器的 cast，运行时也拒绝越界案例。
- 上层 `AnalysisRequest.case_name` 仍为固定二项 Literal，网页 POST 在 admission 之前解析；没有因 repair 两案例扩展而扩大 HTTP schema。
- `tests/test_frontend_cli_commands.py`：`--case output_mismatch` 已合法，所以旧反例失效；改为 `arbitrary_project` 后仍验证真实 argparse 拒绝未知案例，展示命令仍由实际 parser 校验。

### 独立验证

新增 `tests/test_web_admission_case_integration_review.py`，7 项：

1. 三种网页 intent 均尝试提交 `counter_offset`：真实 TestClient 得 400 / invalid_request，完整临时 SQLite SQL dump 不变，无任务创建。
2. 构造合法网页请求与真实 repair-only 注册表相结合的内部错配，使 summary/task/evidence 前置校验均可通过，确保击中新案例门禁。分别测试未取消/已请求取消：`start_created` 和 `_run_started` 调用次数都为0；整个数据库 SQL dump 及数据库文件字节保持不变；claim 未消费、summary revision0、queued、只有created事件、model_calls0。
3. 对原两个网页案例做正控：check_only 正常进入 checking 并结束 check_complete，无模型调用，执行槽可释放。

命令与实际输出：

```text
uv run --frozen pytest tests/test_web_admission_case_integration_review.py tests/test_frontend_cli_commands.py tests/test_web_analysis_store.py tests/test_web_analysis_service_review.py -q
...............................................                          [100%]
```

47 项通过：7 项新增独立测试、4 项 CLI 展示命令测试及36项既有存储/服务独立回归。没有外部模型或 Docker，不能当作真实模型验收。

```text
uv run --frozen ruff check src/agent_workbench/orchestration/runtime.py tests/test_frontend_cli_commands.py tests/test_web_admission_case_integration_review.py
All checks passed!
uv run --frozen mypy src/agent_workbench/orchestration/runtime.py
Success: no issues found in 1 source file
```

## 4. 维度覆盖声明

| # | 维度 | 结果 |
|---|---|---|
| 1 | 架构与边界 | 网页分析与repair案例目录保持独立 |
| 2 | SOLID与设计 | 窄运行时边界，未复制执行逻辑 |
| 3 | 并发与资源 | 拒绝发生在claim消耗之前；既有fence语义未改 |
| 4 | 容错 | 错误case直接拒绝，预取消不掩盖越界 |
| 5 | 性能 | 固定二项成员检查；无新I/O |
| 6 | 安全与合规 | 不扩工具/model/source权限；错误码固定 |
| 7 | 可观测性 | 复用已有admission_invalid错误，不泄露资源内容 |
| 8 | 类型与契约 | Literal缩窄由真实判断建立，mypy通过 |
| 9 | 可测试性 | 独立负例证明SQL/文件字节/事件不变，正控避免全拒绝 |
| 10 | 工程规范 | Ruff通过，旧CLI反例按当前入口同步 |
| 11 | 数据与事务 | 未改变事务；拒绝不消费claim，不写状态 |
| 12 | 依赖治理 | 无新依赖或版本修改 |

## 5. 整改清单

none。没有阻断项或需要豁免的事项。

## 6. 架构防腐与长效治理建议

1. 增加repair case时同时运行本测试，避免共享资源类型扩展意外扩大旧产品入口。
2. 保留同一case的HTTP拒绝与内部claim不变双层测试，前者不能代替后者。

## 7. 审计声明

仅对下列文件中的本轮增量有效。数据库和权限门禁已用真实临时存储验证；未对完整产品、真实模型效果或冻结实验结果下结论。无豁免；所有结论均为已读代码或实际测试。

| 文件 | SHA-256 |
|---|---|
| `src/agent_workbench/orchestration/runtime.py` | `25ebbee4027db3d97da8d0a8773f53903ec605ef40c53a5d26047d1d28b519f8` |
| `tests/test_frontend_cli_commands.py` | `97c2be5503f5a1591c3a72213e23f7b6c077b3a9a205c2bfae4dd0c9d4c656f5` |
| `tests/test_web_admission_case_integration_review.py` | `83cfb400f1921f68670334665c269f162096e996455eee802d54507844b4f154` |
