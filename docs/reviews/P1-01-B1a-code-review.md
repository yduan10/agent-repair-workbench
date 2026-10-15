# 企业代码质量审计报告：P1-01 B1a

- **审计对象**：`web_repairs/*`、`run_store` 的 0008 迁移/结构检查、`repair_store/store.py` 的事务 helper 提取，以及 `repair_store/fencing.py` 的 guard 增量。
- **审计版本**：`cc1c9da` 之后的本地工作区；文末记录最终文件 SHA-256。
- **技术栈**：Python 3.12、SQLAlchemy/Alembic、SQLite、POSIX flock、threading.RLock。
- **业务场景**：General SaaS；本机可信单用户内部存储能力。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-15。
- **独立评审者**：`b1a_code_review`；与实现者分离，只读生产代码，新增独立反例和本报告。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，限此次 B1a 审计范围，不能解释为完整产品已经通过上线验收。
- **上线评估结论**：**Pass，允许 B1a 内部接收能力进入后续集成**。网页开始/停止、模型执行和资源恢复仍须 B1b/B2/B3/B5 各自验收。
- **审计范围**：9 个生产文件（含空包入口）、4 个 B1a 测试文件；约 1,635 行新增/修改/删除，低于本批 2,000 行审查边界。另读取直接依赖，未扩大为全库质量证明。
- **未评估项**：范围内 none。范围外的 HTTP 生命周期、run_created、资源终结/释放、真实模型/Docker、浏览器 UI 不在 B1a，不计通过。

**缺陷汇总**

| 状态 | Defect P0 | Defect P1 | Defect P2 | Defect P3 |
|---|---:|---:|---:|---:|
| 首轮确认 | 0 | 3 | 0 | 0 |
| 修复复审后未关闭 | 0 | 0 | 0 | 0 |

**评分判定轨迹**

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
INITIAL DEDUCTIONS: P1 x 3 x 8 = 24
INITIAL RAW: 76; P1 cap min(76,79) = 76
INITIAL VERDICT: Conditional Pass, blocked by 3 confirmed findings
FINAL DEDUCTIONS: none; all 3 counterexamples fixed and rerun
FINAL SCORE: 100 / 100
FINAL VERDICT: Pass for B1a only
NOT ASSESSED: none within B1a; future stages excluded explicitly
```

## 2. 生产事故风险推演

以下为首轮发现的可复现故障路径，已修复，不表示曾在用户主库发生事故。

> **场景 R1 — 通用响应编码泄漏执行凭证**
> 触发条件：未来 HTTP handler 将内部 RepairAdmission 交给 FastAPI 编码器。初版 claim 是 dataclass，`asdict` 跳过自定义 pickle 拒绝函数，递归产生 token/nonce/owner 字段。用户或日志系统获得本应只在原进程保存的执行凭证。单请求范围；旧测试仅检查 `json.dumps` 和 pickle，未覆盖框架编码器，无自动告警。

> **场景 R2 — 单列回退使同一 claim 二次消费**
> 触发条件：第一次 consume 后、第一项模型预算登记前，错误 SQL 把 consumed 从 1 改回 0。RepairTask 仍 ready/revision0，全部初始摘要仍匹配，第二次 consume 返回 executable=True。单工作区槽边界；旧校验无法从其他行推导该位的历史变化。测试以一条 UPDATE 精确复现，不要求抵御有权限协调改写整库的攻击者。

> **场景 R3 — 等待数据库期间 owner 已被关闭重取**
> 触发条件：consume 入口检查 nonce 后等待 BEGIN IMMEDIATE，另一线程关闭/reacquire owner。旧实现进入事务后不再确认生命周期，向旧 claim 发放执行许可。shutdown/线程并发下单任务范围；无告警，表现为 owner 已改变仍授权启动。独立反例在数据库语句钩子精确安排交错。

## 3. 详细审计明细

### Defect P0 — none

### Defect P1 — 三项已修复并独立复审

#### R1：私有 claim 可被 dataclass/FastAPI 编码器序列化

- **位置**：`src/agent_workbench/web_repairs/models.py:25–58`，初版 RepairAdmissionClaim/RepairAdmission。
- **审查维度**：6 安全；8 契约。
- **置信度**：confirmed。
- **契约**：规格 35 §4 要求 claim 不可序列化、只在原 owner 内存持有。
- **首轮证据**：临时 owner 上 `asdict(claim)['token'] == claim.token` 与 `jsonable_encoder(claim)['token'] == claim.token` 均为 True。
- **最小修法**：移除 claim 的 dataclass 表示；用非 dataclass `__slots__`、不可赋值、拒绝 reduce/copy 的内部能力对象。无需更改安全 receipt DTO。
- **修复结果**：独立测试对 claim 和 admission 的 FastAPI 编码均拒绝；asdict(claim) 拒绝；原有 pickle/日志/数据库不含明文测试继续通过。
- **验证**：`test_private_claim_rejects_framework_serialization`。

#### R2：consumed/cancel 单调状态缺少数据库级保护

- **位置**：`src/agent_workbench/web_repairs/store.py:227–260` 与 `src/agent_workbench/run_store/migrations/versions/v0008.py:17–37`。
- **审查维度**：11 事务完整性；3 幂等性。
- **置信度**：confirmed。
- **契约**：A03/A04 与 B1-13：一次消费与接收列损坏拒绝。
- **首轮证据**：consume → 单列 UPDATE consumed=0 → 原 claim consume，再次成功。反例最初为 `Failed: DID NOT RAISE StoreError`。
- **最小修法**：0008 增加 immutable/monotonic/tombstone 三个触发器，禁止身份重写、consumed/cancel 回退、active 复活和墓碑删除；RunStore 校验每个触发器完整 SQL，缺失即拒绝使用库。
- **修复结果**：写回退被 SQLite 拒绝，原 claim 第二次消费拒绝；取消与墓碑亦不能撤销；删除任一 guard 后读取和消费均 schema_incompatible。
- **验证**：`test_consumed_receipt_cannot_be_rewound_and_replay_claim`、`test_persisted_cancel_and_receipt_tombstone_cannot_be_removed`、三个 `test_missing_database_guard_refuses_read_and_consume` 参数。

#### R3：owner 检查与消费提交间存在生命周期窗口

- **位置**：`src/agent_workbench/web_repairs/store.py:145–149,223–227`、`web_repairs/fencing.py:80–105`，对应 `repair_store/fencing.py` guard 增量。
- **审查维度**：3 并发/资源；11 事务。
- **置信度**：confirmed。
- **契约**：A03/A04、B1-04 的 close/reacquire 后旧 nonce 不可复活。
- **首轮证据**：在 BEGIN IMMEDIATE 前关闭并重新 acquire 原 owner 后，旧 claim 仍消费成功。独立反例最初失败。
- **最小修法**：owner→task 的 RLock guard 跨越数据库等待、事务及提交。其他线程 close 等待 guard；同线程重入 close 拒绝；fork PID 检查在触碰继承 mutex 前执行。
- **修复结果**：旧交错拒绝且 consumed 不变；两项真实线程测试确认 web/task close 均等待消费提交；fork 继承 claim 拒绝，SIGSTOP/SIGKILL 反例保持通过。
- **验证**：`test_owner_reacquired_while_consume_waits_for_transaction_is_rejected`、两项 `test_close_waits_for_consume_commit_guard`。

### Defect P2 — none

### Defect P3 — none

## 4. 维度覆盖声明

| # | 维度 | 未关闭发现数 | 审查结论 |
|---|---|---:|---|
| 1 | 架构与边界 | 0 | 使用已有存储与预算结构，B1a 不绕过 Controller 发起外部执行；未实现释放则保持 active |
| 2 | SOLID 与现代设计 | 0 | 请求/凭证、owner、事务职责清楚；create/finish helper 保留旧公开包装 |
| 3 | 并发与资源 | 0 | R3 关闭；SQLite CAS、唯一槽、跨进程 flock、线程 guard、fork PID 已覆盖 |
| 4 | 容错 | 0 | admit/取消/过期各写点失败整体回滚；无半个 task/receipt；未知提交不重新签发 |
| 5 | 性能 | 0 | 按主键读取、活动部分唯一索引、既有有界事件审计；事务内无模型/容器调用 |
| 6 | 安全 | 0 | R1 关闭；明文 token 不持久化、不通用序列化；安全错误码无原始参数 |
| 7 | 可观测性 | 0 | 内部强类型 receipt 和原 task 事件可检查；用户 HTTP 可观测性属于 B2 |
| 8 | 类型与契约 | 0 | 严格 DTO、canonical 指纹、初始任务摘要/策略绑定；静态检查通过 |
| 9 | 可测试性 | 0 | 独立反例先失败后通过；临时数据库/真实进程，无外部服务依赖 |
| 10 | 工程规范 | 0 | task ID/目录/预算沿用约定，Ruff 已运行，未改生产输入/密钥配置 |
| 11 | 事务完整性 | 0 | R2 关闭；接收与 finished 同事务；迁移逐表字节保真，非空降级拒绝 |
| 12 | 依赖治理 | 0 | 没有新依赖和锁文件变更；未把此次评审当成全供应链漏洞审计 |

## 5. 整改清单与实际验证

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| R1 | Defect P1 | root 实现者 | B1a 验收前 | 已修复，独立复审关闭 |
| R2 | Defect P1 | root 实现者 | B1a 验收前 | 已修复，独立复审关闭 |
| R3 | Defect P1 | root 实现者 | B1a 验收前 | 已修复，独立复审关闭 |

评审者实际执行的最终命令：

```bash
uv run --frozen pytest tests/test_web_repair_review.py tests/test_web_repair_store.py tests/test_web_repair_processes.py tests/test_web_repair_migration.py tests/test_repair_store.py -o addopts='--import-mode=importlib' -q
```

真实输出：`84 passed in 5.28s`。其中独立 reviewer 10 项；不是 84 个真实修复案例。使用真实临时 SQLite 和 OS 进程，零模型/容器调用，未读写用户主库。

定向 Ruff 输出：`All checks passed!`，独立测试格式检查通过。尝试通过清空 addopts 显示汇总时，一次误移除了仓库的 importlib 模式而产生 3 项 collection error；恢复 `--import-mode=importlib` 后以上最终命令通过，未将失败计作成功。全量回归与前端构建由实现者另记交付报告，不冒充本评审者执行结果。

## 6. 架构防腐与长效治理建议

1. **保留独立反例**：框架编码、单调回退、等待事务时关闭 owner 必须随 CI 运行；维护成本为 10 个短用例，防止只验证正常路径。
2. **B1b/B2 接续遵守同一锁顺序**：web owner→task fence→SQLite 短事务；禁止运行期间销毁 owner 或用 GET 重建 claim。它们需要新的生命周期验收，不能引用本报告替代。
3. **迁移必须显式**：0008 是新库版本，旧 0007 的运行服务不得由 GET/启动偷偷迁移。更换常驻后端前另做备份/迁移/保真验收。本轮不动主库。

## 7. 审计声明

- 本报告仅对下面 SHA 集合的 B1a 实现有效。后续生产文件修改必须补增量复审。
- 没有范围内未评估区，没有豁免；三项发现均 confirmed，已复测关闭。
- 不证明公网/多租户部署安全，不承诺外部工具 exactly-once，不证明 B1b 恢复或网页链路已完成。
- 评审者只新增 `tests/test_web_repair_review.py` 和本文；未修改生产实现、提交或推送代码。

### 冻结文件摘要

| 文件 | SHA-256 |
|---|---|
| `src/agent_workbench/repair_store/fencing.py` | `2295a808e932305cc36d4c425a2084f02f2ec5897d894a8f866a05f13fffad8f` |
| `src/agent_workbench/repair_store/store.py` | `6efffb3d603166ad50512b2667a4ba89ffed090bcccee87fa215751a20a71a46` |
| `src/agent_workbench/run_store/migrations/versions/v0008.py` | `5e12068712df3934143fbc8921f541486aa80a81649658c47947b44ac1ba9b3c` |
| `src/agent_workbench/run_store/schema.py` | `b41efad344ce5fd514085988bcf3e2e7f4ec757934a9b08c9edad7be53496b3a` |
| `src/agent_workbench/run_store/store.py` | `53d815ad4606eb6df0b145d3c93c0fec45d7ad7d8bc9e3bd494006f4dd7d896f` |
| `src/agent_workbench/web_repairs/__init__.py` | `706a7f9a90906857380fa30ee17f8941c0ffaf2a0b9b6b82663aef371877caba` |
| `src/agent_workbench/web_repairs/fencing.py` | `c65be07014a0a59e89935245f029b4f3807cf343b4062afea84eb9b7bfa2fdb0` |
| `src/agent_workbench/web_repairs/models.py` | `e093c0de42ef73d392e4e0001d214de897219ff28d89099baa11bbe5697015a7` |
| `src/agent_workbench/web_repairs/store.py` | `5daffa1dd6112ff7424fa3c8314b057c92cc3dda5e37510ff0cf9a6812ac93d5` |
| `tests/test_web_repair_review.py` | `1d33c36d5a39a3318093d79a358f291b00d70b1493a7d9cbcb699fe8037e3090` |

## 8. 最终测试与交付材料增量复审

2026-10-15，同一独立评审者。重新计算上表9个生产文件摘要，全部一致，生产结论维持 Pass。增量只包括旧回归测试调整、5项新测试、文档和前端说明，没有解除新的执行权限。

### 旧测试修正不是放宽生产契约

- `tests/test_web_analysis_store.py::test_0006_upgrade_preserves_rows_and_rejects_nonempty_downgrade`：原断言比较旧表全集，升级到0008后应排除新建的`web_repair_requests`；保留全部旧表内容比较、非空降级拒绝等断言。新表本身由B1a迁移测试覆盖，不删除旧数据保真断言。
- `tests/test_mcp_adapter.py::test_cooperative_cancel_reaps_real_child`：原固定1.5秒可能在握手完成前取消；生产代码区分 sent前transport_error与sent后outcome_unknown，这个区分正确。改为SDK `call_tool`入口事件同步后取消。已追踪`mcp_adapter.py:148–150`的sent赋值先于SDK调用，测试仍调用真实SDK/子进程，仍检查run_cancelled、outcome_unknown、非空PID集及每个进程已经回收，10秒总时限防挂起。它不声称工具端一定已处理请求；unknown语义正是“开始调用后无法证实结果”。同时复跑dispatch前截止测试，保持双边语义。
- 增量看到的一处重复`assert pids`已移除；规格34旧“13项”已更正为14项。无未关闭缺陷。

### 增量实际验证

评审者执行8项：上述两项、dispatch前截止，以及提交确认丢失（admit/consume两分支）、SQLite唯一槽、旧初态拒绝、等待中的并发同请求。结果：**`8 passed in 1.80s`**。这些与前面的84项部分重叠，不相加为独立覆盖总量。

已读取`artifacts/b1a-old-reader-result.json`，并核对探针使用的旧模块字节等于`git show HEAD:src/agent_workbench/run_store/store.py`。评审者另在新临时目录独立重跑旧完整RunStore类读新0008库，输出：`committed 0007 reader rejects temporary 0008: schema_incompatible`。这与修改REVISION的单测是两份不同证据，未操作主库。

### 文档和前端边界

审阅03/34/35/36及docs README，5个文件的本地文档链接均存在。36明确临时SQLite、合成哨兵、内部执行权与网页操作的区别，并保留旧服务/0007主库的迁移边界。审阅时最终全量门禁仍在运行，材料使用in_review及待填结果，没有提前计通过。

`frontend/lib/capabilities.ts`只新增说明注释，repairs仍是web_readonly；`milestones.ts`新增站内接入说明且明确网页仍只读、CLI发起修复。没有给用户展示不存在的开始/审批功能，没有新增开发数字到产品面板。后续填写最终全量/构建计数应以实际日志为依据；这些由实现者运行，不能表述成此评审者独立执行。
