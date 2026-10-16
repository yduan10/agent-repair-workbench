# 企业代码质量审计报告：P1-01 B2 组合资源边界

- **审计对象**：旧复现/分析槽释放判断及 runner/oracle 资源终结错误传播。
- **审计版本**：`a68dde0c8cfd2e82d8ef67dbcd56bd1d752f2ed0` 后的 B2 工作树；文件 SHA-256 见第 7 节。
- **技术栈**：Python 3.12、AnyIO/asyncio、SQLAlchemy/SQLite、受控 Docker。
- **业务场景**：General SaaS。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15。
- **评审者**：独立子 Agent `/root/b2_resource_review`；只修改独立测试与本报告，生产修复由 `/root` 完成。

## 1. 代码质量评估卡

- **综合质量得分**：修复后 **100 / 100**，仅适用于本报告的资源边界子范围。
- **上线评估结论**：**Pass / 本子范围通过**。这不是整个 B2 API、多 worker、HTTP 断连、shutdown 或真实 Docker 组合验收结论。
- **审计范围**：4 个生产文件，24 行增删；追踪直接调用方 `AnalysisStore.reserve_execution`、`ToolRuntime._reproduce`、`AnalysisRuntime.turn`、`compare`、`WebRepairRecovery.release_checked`，未修改其实现。
- **未评估项**：本子范围内 none；B2 新 API/service 的完整行为由另外的独立评审负责。未访问模型网关，未运行真实 Docker。

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 未关闭（2 项已修复） | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 修复后 0；初审 P1×2 = 16
RAW SCORE: 修复后 100；初审 84
CAP APPLIED: 修复后 none；初审 P1 present -> min(84,79)=79
FINAL SCORE: 100 / 100
VERDICT: Pass，仅资源边界子范围
NOT ASSESSED: 本子范围内 none
```

## 2. 生产事故风险推演

### R01：晚到 create 穿越旧槽

- **触发条件**：旧复现/分析任务在 create 已发送但结果未落盘时中断，对账时恰好 inspect 为 absent；或观察到 stopped 但尚未删除的容器。
- **失效机制**：旧 `_release_safe` 把 `reconciled + absent/stopped` 当作释放凭据。新的网页任务随后可以创建容器，旧 create 仍可能到达。
- **用户可见症状**：一个类别同时存在两个受控容器，突破文档 35 第 7 节的“每类最多 1 个”目标。
- **爆炸半径**：同一个状态目录的网页执行槽；CLI/其他目录不在声明范围。
- **可检测性**：旧 ledger 只有一次观察，不能证明 create 已终结；资源数量可观测但没有独立告警。

### R02：资源未知被次要错误覆盖

- **触发条件**：容器删除成功，但 attach 子进程关闭超时，同时发生原始执行错误、后置快照/镜像/协议/验收器校验失败，或外层原生取消。
- **失效机制**：`cleanup=removed` 保留，`attach_cleanup_unconfirmed` 却被覆盖；释放器据此接受终结证据。
- **用户可见症状**：执行资源仍有未确认部分，槽已经允许新任务。历史报告只显示其他错误，丢失应阻止释放的依据。
- **爆炸半径**：复现、分析、修复三种受控执行路径。
- **可检测性**：修复前仅主错误可见；修复后资源未知作为稳定错误保留，并阻止释放。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### R01：对账观察不能证明创建终结 `[confirmed]`，已关闭

- **位置**：`src/agent_workbench/web_runs/store.py` 的 `_release_safe`（原第 64 行）；`src/agent_workbench/web_analyses/store.py` 的 `_release_safe`（原第 115–116 行）。
- **审查维度**：3 并发与资源、11 数据与事务完整性。
- **修复**：删除仅凭 reconciled 释放的分支；只接受 finished 记录、合法绑定报告和正向清理凭据。

```diff
- safe = latest == "reconciled" and run.executor_state in ("absent", "stopped")
+ safe = False

- if latest == "reconciled":
-     continue
```

- **验证**：独立测试分别对复现、分析构造持久接收、执行预留、超时对账；absent/stopped 两种结果共 4 项均保持 active。
- **保守后果**：旧槽没有可靠终结证据时持续拒绝新任务；这不代表已提供通用强制解锁。不能通过编辑 ledger 或把 unknown 改成成功来恢复。

#### R02：attach 终结错误必须贯穿所有收尾层 `[confirmed]`，已关闭

- **位置**：`src/agent_workbench/runner/service.py:163`；`src/agent_workbench/candidate_execution/oracle.py:220`、`:335`、`:404`。
- **审查维度**：3 并发与资源、4 容错、7 可观测性。
- **初审证据**：独立测试先后得到 `4 passed / 1 failed`、`5 passed / 1 failed`、`10 passed / 1 failed`；失败分别证明 runner 主错误遮盖、oracle 后置校验覆盖、run_oracle 原生取消覆盖。
- **最小修复**：runner 的资源错误优先；oracle 用局部 `attach_failed` 保留失败，后置校验后重新赋值；finalize 与三个取消收尾赋值点均保留 attach 未确认状态。

```diff
- execution.error = execution.error or "attach_cleanup_unconfirmed"
+ execution.error = "attach_cleanup_unconfirmed"

+ if attach_failed:
+     report.error = "attach_cleanup_unconfirmed"

- result.error = "run_cancelled"
+ if result.error != "attach_cleanup_unconfirmed":
+     result.error = "run_cancelled"
```

- **验证**：独立反例覆盖原始执行失败、wire/snapshot/image/oracle 后置失败、容器与 attach 双清理失败、native cancellation；均要求 `terminated(report)==False`。Oracle 还要求 `status=outcome_unknown`。没有用伪造 success 掩盖未执行步骤。

### P2 — 主要缺陷

none。

### P3 — 次要缺陷

none。

### 已核对且不存在的两个疑点

1. **分析 pending T05 不会因 summary 遗漏而释放**：`AnalysisStore.reserve_execution` 在同一事务内写入 tool_started、summary.execution_record_ids、run/claim 和 execution link，然后才调用 `run_sandbox`；`_get` 会核对 links 与 summary。独立测试在 finish 前确认 run 已进入 summary，并证明对账后仍阻止释放。
2. **同一活动槽不会在未知执行后继续创建下一个容器**：`ToolRuntime._reproduce` 将任何执行未知映射为 `RESULT_UNKNOWN`；`AnalysisRuntime.turn` 随即 Stop。修复控制器遇未知/需要对账停止；T07 `compare` 对 cancelled/outcome_unknown/inconclusive 立即 break，且先保存当前结果再进入下一格。原生取消通过 owned AnyIO scope 进入执行层，不直接取消其清理 worker。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 备注 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 释放权仍由 host ledger/recovery 持有，不由模型报告决定 |
| 2 | SOLID 与现代设计 | 0 | 局部故障优先级修复，无新增平台抽象 |
| 3 | 并发、异步与资源安全 | 2 已关闭 | 对账观察及 attach 收尾 |
| 4 | 容错与防御性编程 | R02 已关闭 | 多重故障及取消顺序均保留资源未知 |
| 5 | 性能、伸缩性与计算效率 | 0 | 失败关闭策略不增加查询/执行循环 |
| 6 | 安全与数据合规 | 0 | 固定错误码；测试不访问凭据/模型 |
| 7 | 可观测性与运维友好度 | R02 已关闭 | 未知清理不再从报告中消失 |
| 8 | 类型安全与契约表达 | 0 | 沿用已存在枚举，未修改公开 schema |
| 9 | 可测试性与死代码 | 0 | 11 项独立反例使用临时 SQLite/快照与受控 fake |
| 10 | 工程规范与一致性 | 0 | Ruff 通过；生产代码由实现者修改 |
| 11 | 数据与事务完整性 | R01 已关闭 | pending T05 原子关联与安全释放已追踪 |
| 12 | 依赖与供应链治理 | 0 | 无新增依赖或 lockfile 修改 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| R01 | Defect P1 | `/root` | B2 验收前 | fixed + independently rechecked |
| R02 | Defect P1 | `/root` | B2 验收前 | fixed + independently rechecked |

独立测试：`tests/test_b2_resource_review.py`，11 项。

验证命令：

```sh
uv run --frozen pytest tests/test_b2_resource_review.py tests/test_sandbox_lifecycle.py tests/test_candidate_oracle.py tests/test_candidate_comparison.py tests/test_web_analysis_ledger_review.py -ra
uv run --frozen ruff check tests/test_b2_resource_review.py src/agent_workbench/runner/service.py src/agent_workbench/candidate_execution/oracle.py src/agent_workbench/web_runs/store.py src/agent_workbench/web_analyses/store.py
```

最终复跑原始结果：`122 passed, 3 skipped in 3.07s`；其中本轮独立反例 11 项全部通过，3 项跳过为 `tests/test_candidate_comparison.py:303: explicit Docker gate`。Ruff：`All checks passed!`。真实 Docker 标记用例未执行，不能计作真实组合资源验收。

## 6. 架构防腐与长效治理建议

1. 保留“主执行错误 + 资源终结证据”区别。当前以资源未知优先实现 fail-closed；未来如拆独立字段，必须同时升级报告 schema、审计和释放规则，不能只改 UI。成本为一次受控迁移。
2. 每次引入新的取消/后置验证层，都运行本文件的组合故障测试。成本约数秒，防止新增赋值重新掩盖资源未知。
3. B2 总体验收继续执行三类网页槽同时占用、unknown 后新请求拒绝、T07 串行数量探针。此报告证明局部释放条件，不用“各自有锁”替代组合实验。

## 7. 审计声明

- **范围版本 SHA-256**：

| 文件（`src/agent_workbench/` 下） | SHA-256 |
|---|---|
| `runner/service.py` | `97b732393ad266ca89766dab337d157dcb9b3221efbd80881d74e523083948f6` |
| `candidate_execution/oracle.py` | `4cf5515c02dcdb1fc925c45aed7057f5fb56d380835c88119a21f6faf8fb9d7e` |
| `web_runs/store.py` | `9f792348d676ac13fef393fbe0f94dd7d8c2f4d1000c3a0bed718dd0a265c59c` |
| `web_analyses/store.py` | `e51aff9eb6a509367252ebf6f20fe299a1dc2e97e091dd1fe8acc89035fb26ab` |

- 后续修改以上文件会使对应结论需要增量复审；oracle/runner 属于 oracle 源码闭包，新进程会得到新的 ORACLE_SHA256。旧证据不得重写为新版本。
- **未评估**：真实 Docker 和新 B2 API/service 全量行为不属于本子批通过结论。
- **已施加豁免**：none。
- **置信度**：所有缺陷均有明确执行路径/反例，未用 suspected 项驱动结论。

### 收尾增量复核：旧断言与三槽组合（2026-10-15）

独立复核了 `tests/test_web_admission.py` 与 `tests/test_web_analysis_store.py` 的两处旧断言修改。原断言要求 `reconciled + absent` 允许释放，与文档 35 第 7 节“未知 create 不释放”冲突；改为拒绝新的复现接收/保留分析 active 是必要的契约修正，没有删除故障注入或跳过失败测试。

正常安全路径仍有对应覆盖：

- 复现 `test_cancel_persistent_and_idempotent`、`test_prune_excludes_active_then_retains_tombstone` 仍要求 finished + removed 的合法报告允许释放。
- 分析 `test_terminal_analysis_requires_current_safe_report_for_finished_execution[safe]` 仍允许正向清理报告释放；无容器的正常结束、执行前取消、check_only 都保留释放断言。
- `test_safe_slot_release_preserves_unknown_model_reservation` 保留“模型费用未知、没有容器”安全释放与原 token 预留不变的断言，未把所有 unknown 一概永久占槽。

已阅读并运行新增 `tests/test_b2_combined_slots.py`。它使用同一临时状态目录、真实三类 service/store、确定性模型与 Docker/oracle 边界，验证：三个不同类别同时被接收；分析与修复两个模型边界同时等待；三个受控执行边界各进入一次；同请求重放只读；资源未知后旧 active 均保留，三类新请求均被拒绝，模型调用数量仍各为一次。

**证据边界**：这是单事件循环下的真实服务/账本组合与被替换外部边界测试。模型峰值集合按类别计数，证明分析和修复同时等待，不独立证明某类别不存在重复 HTTP；此项还依赖已审查的串行 runtime。它不运行真实 Docker，不测 Docker daemon 的晚到 create，不测真实 HTTP/CPU/内存配额，也未执行 T07 四格。本报告不把它表述为真实模型或真实容器压力验收。多 worker/HTTP/shutdown 由 B2 其他用例提供。

```sh
uv run --frozen pytest tests/test_web_admission.py tests/test_web_analysis_store.py tests/test_b2_resource_review.py tests/test_b2_combined_slots.py -ra
```

原始结果：`55 passed in 11.57s`。本次复核的 4 个生产文件 SHA-256 与上表一致。结论维持：本资源子范围 Pass，无新增未关闭 Defect P0/P1。
