> **2026-10-13 复审覆盖结论：100/100，设计范围 Pass。** 下述94分是初稿历史结果。P004-D01由第6节统一状态映射/提交失败规则关闭；P004-D02由第3节精确prune资格及第6节unknown资源刷新规则关闭。新快照见 P0-04-design-snapshot.txt。此设计通过不等于代码/产品完成。

# 企业质量审计：P0-04 设计预审

- **范围**：docs/14-run-store.md 初稿（53行），对照AGENTS、docs/01、03、04；不评未提供的实现。
- **版本**：2026-10-13，SHA-256见 `P0-04-design-snapshot.txt`。
- **审查目录**：`<review-workspaces>/p0-04-review`。
- **技术栈**：SQLAlchemy 2.0、SQLite WAL、Alembic、既有受控Docker runner、FastAPI只读接口。
- **场景/严苛度**：General SaaS / Mission-Critical。
- **方法**：文档约束对照、失败时序推演及官方事务资料核对；未更改实现、未建镜像、未清理资源。

## 1. 质量评估卡

**94 / 100，Conditional Pass：范围可行，两项状态语义缺口应在规格冻结前补齐。**

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 2 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 2 confirmed document contract gaps × P2(3) = 6
RAW SCORE: 94
CAP APPLIED: none
FINAL SCORE: 94 / 100
VERDICT: Conditional Pass — P2 allowance is zero; specification amendments required
NOT ASSESSED: implementation, runtime concurrency/fault injection, migrations, API/UI; later review batches
```

设计中已经明确且应保留的部分：报告BLOB与terminal/event同一SQLite事务；claim先持久化再启动；固定短租约且不自动重投unknown；元数据DTO不含token；显式迁移、只读页面、prune默认dry-run。报告小于1MiB时采用同库原子提交，比引入文件/数据库双写协议更适合本阶段；不需要新增队列或平台组件。

## 2. 事故风险推演

无已确认P0/P1实现缺陷。以下是设计缺口的可达时序，不能误述为现有代码已出错：

- 已收到合格工具结果，但cleanup未确认；若协调层只看contract passed，数据库/UI可能写succeeded。规格必须提供完整终态映射，阻止这种解释。
- 过期running第一次对账时daemon失联，记录unknown/unavailable。若reconcile只扫描running，稍后资源已回收也无法刷新记录，prune永久排除；若为解决此问题将unknown一律删，又会删除仍有未决资源的记录。

## 3. 详细审计明细

### P0

none。

### P1

none。尚未审实现，不臆测CAS或事务已写错。

### P2 — P004-D01：新运行终态缺少映射契约

- **位置**：docs/14-run-store.md:20–24。
- **维度**：8 类型与契约；11 数据完整性。
- **置信度**：[confirmed]，文档列出terminal枚举但未定义与SandboxReport/cleanup/storage failure之间的映射。
- **缺口**：CLI既有exit2可表示拒判、调用结果未知、清理失败、数据库保存失败，不能直接映射同一业务状态；cancelled也需与已dispatch后的unknown区分。
- **最小补充**：增加统一映射表，覆盖成功+removed、业务失败、调用前拒绝/取消、调用后取消/丢响应、结果已收但清理未确认、finish写失败。后者明确不提交succeeded、不伪造terminal，CLI退出2，由后续对账保守处理。
- **验收**：表格每行对应一项协调层测试；UI只消费该统一状态，不再自行按exit code重解释。

### P2 — P004-D02：unknown资源刷新与prune资格不闭合

- **位置**：docs/14-run-store.md:28–32。
- **维度**：4 容错；11 数据完整性。
- **置信度**：[confirmed]，reconcile仅描述过期running，未定义已unknown记录的后续资源更新；“无未决清理风险/超过期限”没有精确谓词。
- **最小补充**：允许unknown记录继续做只读资源探测/CAS更新，业务终态始终unknown，不重投；明确absent、stopped、running、unavailable、mismatch及模糊create分别是否可prune。明确保留期采用哪个时间，dry-run与apply都在事务内重新核对资格。stopped与removed不能无解释混用。
- **验收**：running过期→unknown/unavailable→unknown/可靠清理→允许或明确仍禁止prune；再次探测无工具执行。另测运行中/模糊创建/清理未确认始终排除，以及dry-run候选改变后apply重查。

### P3

none。

### 实现必须落实的边界（并非当前已确认代码缺陷）

1. **事件幂等不等于执行许可重放**：重复claim/event不能向另一个调用方返回可再次启动的lease；本阶段不重新执行已有run。两个进程领取需断言只有一个“允许启动”的结果。
2. **原子CAS**：claim/finish的status/version/attempt/token/lease判断与更新在同一写事务/条件更新中；读取后无条件写回不可接受。finish迟到拒绝且不留下artifact孤儿。
3. **持久时间**：说明时间来源、单位和lease比较时点。跨进程/重启使用可持久比较的时间；测试过期边界和时钟调整，不能将进程monotonic数值当跨重启时间戳。
4. **实际SQLite事务**：Python3.12 sqlite3默认legacy模式不会对SELECT自动BEGIN；只写SQLAlchemy事务上下文不必然实现多次SELECT的稳定snapshot。必须明确驱动事务模式/显式BEGIN，并用并发prune验证读取原子性；migration也不能因DDL隐式行为留下半迁移。依据：[SQLAlchemy SQLite事务说明](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver)。
5. **迁移并发与失败**：两个首次CLI并发init、busy、未知revision、升级中断均在执行前失败闭锁；不因“DB文件已存在”跳过schema检查。降级有记录必须拒绝，并保留旧数据。迁移细节参考：[Alembic SQLite批次迁移](https://alembic.sqlalchemy.org/en/latest/batch.html)。
6. **读库与权限**：读API不创建库、不运行迁移；不仅DB，WAL/SHM及目录权限也需验证。拒绝异常路径/符号链接，不为修权限而更改无关用户目录；AWB_STATE_DIR只影响明确项目状态目录。
7. **事务副作用边界**：enqueue/claim失败时0次Docker启动；finish失败后只报告存储失败，不再次call。真实子进程SIGKILL在claim后/创建ACK前/结果前/提交前覆盖，允许留下可对账unknown，绝不自动恢复执行。
8. **产物和隐私**：写入时限定SandboxReport schema与大小，读取时校验hash/size/schema；lease_token在DTO、event、report、错误、下载均不存在。report内部执行ID应准确关联attempt，不能把run_id与Docker attempt UUID混用。
9. **恢复安全**：Docker只读精确attempt探测；name/tag不匹配则mismatch而不是absent；lease过期不授权删除活跃容器。CAS冲突不得覆盖刚完成的合法terminal。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构边界 | 小报告同库原子保存，分离store与runner，方向清楚 |
| 2 | SOLID/设计 | 不增加平台；公共状态由store定义 |
| 3 | 并发/资源 | CAS/lease方向合理，实现待多进程验证 |
| 4 | 容错 | D02恢复刷新缺口 |
| 5 | 性能 | 小BLOB/短事务/查询上限合理；容量未测 |
| 6 | 安全/合规 | 明确不存原值，不公开token；路径/WAL权限待实现 |
| 7 | 可观测性 | 版本化事件/来源摘要明确，不使用用户文本 |
| 8 | 类型契约 | D01终态映射缺口 |
| 9 | 可测试性 | 矩阵含真实DB故障/重启；补上述时序反例 |
| 10 | 工程规范 | 分批review、ADR需同步原架构 |
| 11 | 数据完整性 | BLOB+terminal事务合理；D01/D02交接需冻结 |
| 12 | 依赖治理 | 指定锁定SQLAlchemy/Alembic，实际锁及迁移待代码评审 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P004-D01 | Defect P2 | `/root` | 协调/UI状态契约冻结前 | open |
| P004-D02 | Defect P2 | `/root` 与 `/root/docs_review` | store接口冻结前 | open |

## 6. 长效治理建议

1. 统一终态映射表作为实现与回归依据，避免CLI/API/UI各自解释退出码。
2. 固定多进程CAS、提交失败、晚到worker、unknown资源刷新与prune反例；记录至少一个完整重启时序。
3. 保留“状态事实”和“执行资源观察”的分离；后续P0-05长任务前再新增心跳，不提前扩成通用调度平台。

## 7. 审计声明

这是规格预审，不是实现通过或P0-04完成。两项发现仅指文档契约缺口，不指控尚未提供的代码发生过故障；未评分未审代码。完成补充后复审文档，之后分别审store/迁移、协调/API、UI。未修改实现或构建镜像，无清理任何容器/数据库。

## 复审关闭记录

| ID | 结论 | 修复证据 |
|---|---|---|
| P004-D01 | closed | docs14第6节：结果/取消/清理/提交失败逐项映射；双ID保存约束 |
| P004-D02 | closed | docs14第3、6节：unknown可再次观察但不重投；终态updated_at、absent、有效报告与确认cleanup的精确删除资格 |

当前评分100−0=100，无封顶、无剩余P0/P1/P2/P3；仅设计通过。原始缺口与建议保留为审计历史。
