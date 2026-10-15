# 企业代码质量审计报告

- **审计对象**：P1-01b B1 网页分析接收账本、0007 迁移、AnalysisRuntime 启动入口拆分。
- **审计版本**：独立目录 `agent-sandboxes/web-analysis` 的 `artifacts/b1-files.json`，清单 SHA-256 `3160c952072d090838878f6d72a72990d6ea81c8bbb8551d4b26263f86183a36`；结束时 10 个文件摘要全部匹配。
- **技术栈**：Python 3.12、SQLAlchemy/SQLite、Alembic、LangGraph、POSIX flock。
- **业务场景**：General SaaS；实际产品边界为本机可信单用户工具。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14（Asia/Shanghai）。
- **独立评审者**：`p006_contracts`；未参与该批实现。参考 `auditing-enterprise-code-quality` skill。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，本批无已确认未解决缺陷；不是整体项目质量或上线成熟度评分。
- **上线评估结论**：**Pass：允许 B1 整合**。不代表 P1-01b 网页执行功能已经验收。
- **审计范围**：清单 10 个文件，约 1208 新增行；包括接收/取消/释放、迁移与 runtime 拆分。另新增 1 个独立反例测试文件。
- **未评估项**：本批范围内 none。B2 HTTP/lifespan service、B3 前端控制台、B4 真实模型和容器端到端验收明确在范围外，须各自通过门禁。

**缺陷汇总**

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

**评分判定轨迹**

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
DEDUCTIONS:   none -> sum = 0
RAW SCORE:    100
CAP APPLIED:  none
FINAL SCORE:  100 / 100 (B1 scope only)
VERDICT:      Pass - no confirmed unresolved defect in B1
NOT ASSESSED: none within B1; B2/B3/B4 excluded by review boundary
```

## 2. 生产事故风险推演

本次无 P0/P1。针对已声明的不变量验证了以下故障路径：

- **同一接收 claim 被两个调用者竞争消费**：真实 SQLite 事务只允许一个 queued→checking 转移；另一调用得到 `admission_invalid`，只出现一个 phase_changed 事件。
- **迁移创建表之后、创建唯一索引时失败**：故障注入后表和版本号均回滚到 0006；再次显式迁移可成功，旧运行数据保持相同。
- **模型终态但工具清理未确认**：检查所有关联执行的终态、executor_state、最终报告或明确 reconciled 事件；清理未知不释放活动槽。模型计费用量未知但无关联运行时，可以释放本地执行槽，预留额度仍保留。
- **进程暂停/被杀**：原批实际子进程测试确认 SIGSTOP 不释放 owner/task 锁，SIGKILL 后墓碑不发放新 claim；只允许显式对账，不恢复模型循环。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 验证证据

在独立目录运行，全部数据库为临时库；未修改主库、未启动网络模型、未将合成报告算作真实容器运行。

1. 原批账本与既有分析/runtime 回归：

```sh
PYTHONPATH=src python -m pytest tests/test_web_analysis_store.py tests/test_analysis_store.py tests/test_reviewer_analysis_store.py tests/agents/test_runtime.py tests/agents/test_runtime_reviewer.py tests/agents/test_runtime_handoff_review.py
```

```text
82 passed in 14.00s
```

2. 既有 CLI 与 RunStore 回归：

```sh
PYTHONPATH=src python -m pytest tests/test_cli.py tests/test_run_store.py tests/test_run_store_concurrency.py
```

```text
53 passed in 18.89s
```

3. 独立反例 `tests/test_web_analysis_ledger_review.py`：

```sh
PYTHONPATH=src python -m pytest tests/test_web_analysis_ledger_review.py
```

```text
6 passed in 1.40s
```

覆盖并发消费、迁移中断回滚、cleanup/create/attach 三种不确定错误、取消不消耗或销毁接收 claim。初次反例将 `create_unconfirmed + executor absent` 作为可落账状态，但现有 RunStore 已更早拒绝该组合；修正独立测试为断言 `invalid_status` 和活动槽保持，不构成生产缺陷，也未修改生产实现。

4. 10 个冻结文件加独立测试的 Ruff 和格式检查，以及 9 个冻结源码的无缓存 mypy：

```text
All checks passed!
11 files already formatted
Success: no issues found in 9 source files
```

以上是分开的实际运行，不能合并宣传为一次完整项目全量测试。独立反例 SHA-256：`6d9136f1c597552b61fa9e55ddf9fe67ca39da116eab5a4224a38086e2bea63a`。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 新网页接收和旧 CLI 分入口，公共执行体复用；没有 HTTP handler 混入本批 |
| 2 | SOLID 与现代设计 | 0 | 原子 create 提取为同连接 helper，未复制模型循环 |
| 3 | 并发、异步与资源安全 | 0 | owner→task 锁序、SQLite 单次 claim 消费、部分唯一索引；实测竞争/暂停/死亡 |
| 4 | 容错与防御性编程 | 0 | 接收/消费故障回滚；异常不伪造成功，不自动恢复外部操作 |
| 5 | 性能、伸缩性与计算效率 | 0 | 本机单槽有界分析；按 task 主键读；最多 20 个关联执行 |
| 6 | 安全与数据合规 | 0 | 固定案例/意图/预算；私有 token 仅摘要持久化；无新增凭据/原文日志 |
| 7 | 可观测性与运维友好度 | 0 | active/cancel/consumed 和结构化事件可追溯，未知状态保留 |
| 8 | 类型安全与契约表达 | 0 | 严格 request、summary/registry 绑定和一次性私有 claim |
| 9 | 可测试性与死代码 | 0 | 无网络 fake adapter、真实 SQLite 和子进程锁测试；新增独立反例 |
| 10 | 工程规范与一致性 | 0 | 冻结范围和源码哈希已核对；Ruff/format/mypy 通过 |
| 11 | 数据与事务完整性 | 0 | summary/event/receipt 原子创建；consume/phase 原子更新；迁移保真与失败回滚 |
| 12 | 依赖与供应链治理 | 0 | 无新增依赖或自动下载；复用锁定依赖 |

## 5. 整改清单

none；没有待关闭的 Defect P0/P1。

## 6. 架构防腐与长效治理建议

1. **保持接收 claim 作为唯一网页执行权**：B2 只将首次 admission.claim 交给 owner；重复 HTTP 请求必须走 existing() 返回历史。成本为 service/API 负向测试，防止重新引入重复模型/工具执行。
2. **恢复和槽释放分别验证**：B2 的恢复路径必须先确认每个关联执行资源，再对账分析和调用 release_safe；不把 analysis outcome_unknown 当容器已消失。成本为既定停止/死亡/实际 Docker 集成测试。
3. **将本批独立反例纳入默认 pytest**：随 B1 一起复制测试文件，后续修改迁移、claim 或释放条件时继续运行。成本低，能发现消费和迁移事务边界回退。

## 7. 审计声明

- 已审计版本由上述清单冻结；代码发生变化须复核增量。报告允许 B1 整合，不批准整个网页功能或公开发布。
- B2/B3/B4 是明确分批的独立评审范围，不属于本批遗漏项；不能借 B1 Pass 提前标记父里程碑 done。
- 已施加豁免：none。
- 置信度：结论来自实际源码路径、冻结摘要和上述执行证据；未把实现者自评当作独立评审。
