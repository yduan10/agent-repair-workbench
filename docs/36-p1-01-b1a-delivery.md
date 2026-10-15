# P1-01 B1a：网页修复接收账本

2026-10-15。Feature P1。状态：planned → ready → in_progress → in_review → done。父任务P1-01继续in_progress，B1b尚未实施。实施依据：[B1详细契约](35-p1-01-b1-admission.md)。

## 1. 本批交付范围

本批建立网页执行所需的内部接收与授权基础。它不增加HTTP写入口，不调用模型或Docker；网页「修复」继续查看CLI生成的候选与回归结果。

| 组件 | 本批实现 | 使用边界 |
|---|---|---|
| `web_repairs/models.py` | 严格request_id/case_id/mode、固定预算、私有claim及安全receipt | 两个审核案例，单/三角色模式；不接收路径、命令或模型配置 |
| `web_repairs/fencing.py` | 专用POSIX owner锁，PID、nonce、inode核对 | 同状态目录单活动修复；fork、关闭再获取不能继承旧claim |
| `web_repairs/store.py` | 原子admit、existing/receipt、consume、持久cancel | 重复请求不给新claim；提交结果未知时只读核对 |
| `repair_store/store.py` | 抽出同Connection的create/finish私有helper | 旧CLI仍经原公开方法，自行开启事务 |
| `repair_store/fencing.py` | task锁生命周期guard | web→task→SQLite；持guard时其他线程close等待 |
| `0008_web_repairs` | additive接收表、活动槽唯一索引、不可变与单调触发器 | 显式迁移；启动/GET不升级数据库 |

接收时由宿主时间写入started_at；候选准备或调用方传入的旧时间不用于重设运行期限。消费时超过600秒立即记录budget_exceeded；此前已持久取消则记录cancelled。这两条终止路径将consumed、task和finished事件一起提交或一起回滚，不返回可执行授权。消费后到来的取消保留持久标志，实际执行循环处理属于B1b/B2。

正常消费只改变接收账本，任务仍是ready/revision0；一次性由consumed的CAS及数据库单调触发器共同保证。历史请求复用先于当前模型/策略校验，不给旧请求换策略。私有claim不进入事件、报告或HTTP DTO，通用dataclass/JSON/pickle编码均拒绝展开。

## 2. 独立评审与实现加固

使用企业代码质量审计skill，评审者独立于实现者。初审发现三项Defect P1，已修复并进行独立反例复测，最终结论见[代码评审报告](reviews/P1-01-B1a-code-review.md)。

1. 通用框架编码器可以展开dataclass私有令牌：改成非dataclass、不可变slots能力对象，拒绝序列化与复制。
2. consumed单列回退可能复活尚处于revision0的旧claim：增加immutable、monotonic、tombstone三类SQLite触发器；每次事务校验触发器定义。停止标志不回退，活动槽不复活，墓碑不可直接删除。
3. 等待SQLite事务期间owner关闭/重新获取使旧nonce过期：web/task两个锁增加生命周期guard，覆盖事务等待、写入和提交。同线程重入close被拒绝，其他线程close等待临界区结束。

这些检查面向可信本地单用户下的错误操作与程序竞态；不承诺抵御恶意进程同时重写整个SQLite、事件和摘要。B1b还必须持续持有执行锁直到运行和资源核对结束。

## 3. 验收证据与契约对应

测试均在临时目录使用真实SQLite及OS进程/文件锁，未迁移用户主库，没有模型或容器执行。

| 契约 | B1a覆盖 | 留给后续的部分 |
|---|---|---|
| B1-01 | task/event/receipt逐点失败；取消/超时三个写步骤共同回滚；提交后确认丢失 | HTTP断连属于B2 |
| B1-02 | 同参复用、异参冲突、CLI同ID、缺任务墓碑 | 浏览器pending恢复属于B3 |
| B1-03 | 真实spawn两进程同/不同ID竞争、双线程接收/消费、SQLite部分唯一索引 | 多worker HTTP属于B2 |
| B1-04/05 | 伪造token、错误case/mode/policy/初态、目录/nonce、fork、重新获取、重复消费 | run_created入口整体校验属于B1b |
| B1-06/08 | 消费前取消/超时零调用授权、消费后保留停止标志、时钟倒退拒绝 | 已发送调用预算结算及循环停止属于B1b |
| B1-07 | SIGSTOP持锁、SIGKILL后记录保留、无新claim、不自动重放 | 运行中容器恢复属于B1b |
| B1-09 | 0007→0008旧表BLOB/rowid顺序/计数保真；DDL失败回滚；非空禁止降级；旧读者拒绝新版本 | 用户主库迁移另行停写、备份和核验 |
| B1-13 | 元数据篡改拒绝；单调触发器；触发器缺失拒绝；私有令牌编码拒绝 | 运行期T05/T07证据继续沿用既有审计 |
| B1-10/11/12/14 | 本批不声称完成 | controller共享循环、正向终结依据、安全释放、迟到create均属于B1b |

迁移保真测试为每个旧SQL表写入至少两行合成存储哨兵，包括canonical JSON BLOB。它验证存储字节、计数与顺序，不把哨兵称为可执行领域报告；旧领域行为由原有回归测试覆盖。另从已提交基线读取旧RunStore源码，在独立临时0008库上确认返回schema_incompatible。

执行命令：

```bash
uv run --frozen pytest tests/test_web_repair_store.py tests/test_web_repair_processes.py tests/test_web_repair_migration.py tests/test_web_repair_review.py
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv lock --check
```

最终验收：

| 验证 | 实际结果 | 本地产物 |
|---|---|---|
| 全量Python回归 | **1454 passed / 66 skipped**，163.71秒；跳过项不计通过 | `artifacts/b1a-python-final.log` |
| B1a及两项旧测试定向验证 | **60 passed**，5.73秒；包含全量结果，不重复累计 | `artifacts/b1a-final-targeted.log` |
| 独立反例及旧RepairStore回归 | **84 passed**；新增独立反例10项，后续增量8项复跑通过 | [独立报告](reviews/P1-01-B1a-code-review.md) |
| 静态检查 | Ruff/格式379文件、mypy128源文件、uv锁检查通过 | 复跑上方命令 |
| 前端 | production build通过；文档目录/交叉链接1项通过：125页、119个站内链接、零断链 | `artifacts/b1a-frontend-build.log`、`artifacts/b1a-doc-links.log` |
| 旧版本读取器 | 基线完整0007读取器在独立0008库拒绝读取；reviewer独立复验 | `artifacts/b1a-old-reader-result.json` |

独立代码评审及增量复审Pass，三项初审P1全部关闭，无未关闭P0/P1/P2。新增能力只以临时SQLite/真实进程验证，不宣称新增模型修复成功率或网页链路完成。本地产物均不进入源码仓库。

初轮失败也保留：spawn测试夹具最初缺导入路径/信号量持有引用；首次全量在reviewer文件写入过程中出现导入错误；后续全量出现旧迁移测试未排除新增表以及取消测试固定1.5秒启动假设两项失败。最终修正未改变生产MCP逻辑，取消仍在SDK派发边界触发并检查真实子进程回收。完整最终回归已通过，未用单测重跑替代全量结果。

## 4. 迁移与当前服务

当前源代码要求0008；运行中的既有服务仍使用上一版代码及0007主库，本批不重启该后端、不迁移主库。前端站内文档可以更新，修复能力仍为网页只读。

在后续启用新版后端前，需要停止写入、一致性备份、显式运行既有`uv run --frozen agent-workbench runs init`迁移命令，并核对所有旧表内容。不能直接重启新版后端后期待GET自动升级。非空接收表不允许降级；需要回退程序时，不能丢弃接收墓碑来满足旧版兼容。

## 5. 下一批与限制

下一批B1b接通`run_created`与旧CLI共用的执行循环，验证实际取消/预算边界，加入有正向资源终结依据的安全释放。当前B1a故意不提供release_checked：即使接收后取消或超时，active仍保留；只有B1b完成资源核对后才能释放。不能用删除接收行或强制解锁绕开。

随后依次是B2开始/停止API、B3现有修复页操作区、B4审阅决定与补丁下载、B5真实链路验收。当前没有新增可点击的开始/审批按钮，没有增加新的产品Agent或改变既有模型。
