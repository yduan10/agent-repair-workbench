# P1-01a 第一批后端独立评审

- 日期：2026-10-14。范围：存储、迁移及跨进程执行锁；具体文件见 `P1-01a-store-snapshot.sha256`。
- 方法：auditing-enterprise-code-quality，General SaaS / Mission-Critical。实现者与 reviewer 分离，在独立副本验证，未修改实现。
- 对照：22 规格 W02/W04/W05/W06/W07；其他用例涉及的 API、执行服务和 UI 不属于本批。

## 1. 代码质量评估卡

**Pass，仅本批冻结文件。** 无已确认 P0/P1/P2/P3。评分 100/100：100 减 0，无封顶；不表示完整 P1-01a 功能通过。

主项目既有存储/并发/持久化和本批 admission 共 65 项独立运行通过。新增两项独立探针通过：真实 SIGSTOP/SIGKILL 锁生命周期、完整旧版运行及报告升级保真。新服务及真实 Docker 验收留下一批。

## 2. 生产事故风险推演

未发现残余 P0/P1。设计 D01 的风险在本批已具备控制基础：文件锁独立于 lease；过期的活跃 Web 运行在 CLI 对账时同样需要锁。API/worker 是否全生命周期持锁，须由第二批代码与测试继续证明。

## 3. 详细审计明细

- `web_runs/store.py`：admit 在同一写事务内保存 run、claim、两事件与 request 映射；claim/映射失败回滚无残留。已有 request 只返回 RunView，不再次授权 claim；异参数拒绝。
- `run_store/migrations/versions/v0002.py`：active 部分唯一索引控制跨进程数据库槽；两个布尔列有约束；映射故意不使用随 run 删除的外键，去重墓碑持续保留。
- `run_store/store.py`：0001 仅在显式初始化迁移路径接受；旧版本读接口拒绝，不隐式迁移；prune 排除 active Web 记录；空库降级检查新表。
- `web_runs/store.py`：释放槽须持 OwnerFence，并核对终态、最新事件、资源状态及报告；报告缺失、清理不确定、保存失败均保留槽。取消仅置持久标志，不能伪造终态。
- `web_runs/fencing.py`：非阻塞 flock，锁文件拒绝符号链接，fd 为 CLOEXEC；异常关闭 fd，OS 进程结束后释放锁。不支持的平台拒绝，不用内存锁冒充跨进程保护。
- `run_store/execution.py`：对 active Web 记录先获取同一 fence，再 inspect 和 CAS 对账；锁忙不登记 absent。Web 锁不对用户独立 CLI 并发作承诺。
- `web_runs/models.py`：四场景严格枚举、规范 UUID、固定 seed/lifetime/case；请求摘要包含版本及规范配置/case 摘要，与仓库固定例一致。

最终微增量已核对：纯 `locking_supported()` helper；admit 在 Web 映射缺失但 CLI run ID 已存在时返回 request_conflict，不继承 CLI 身份。新增碰撞测试后，本批 13 项加独立 2 探针共 15 项重新通过。

### 独立执行证据

```text
uv run --frozen pytest tests/test_web_admission.py tests/test_run_store.py tests/test_run_store_concurrency.py tests/test_run_persistence.py -q
.................................................................        [100%]

uv run --frozen pytest tests/test_reviewer_web_store.py -q
..                                                                       [100%]
```

独立探针文件 `tests/test_reviewer_web_store.py`：

1. spawn 子进程实际持锁，父进程发送 SIGSTOP 并通过 waitpid 确认已暂停；另一锁申请必须 runner_busy；SIGKILL 后 join，再次锁申请成功。
2. 保存带 attempt、事件、报告 BLOB 的完整记录，将无 Web 数据库退回 0001 后升级；四张历史表逐行及报告原字节完全一致，读取报告及摘要不变，随后能接收新 Web 运行。

最初独立探针的 spawn 模块路径缺失属于测试装配错误，补充项目测试路径后通过，未修改生产实现。首次回归命令误写一个测试文件名，纠正为 `test_run_persistence.py` 后完整运行，不把错误命令计为通过。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | 存储与 Web admission 分离；执行服务留第二批 |
| 2 | SOLID | 共用事务内 create/claim 保留原 CLI 行为 |
| 3 | 并发与资源 | 部分唯一索引、CAS、flock、真实多进程和停止/死亡探针通过 |
| 4 | 容错 | 回滚、缺报告、不确定清理及保存失败保持拒绝分派 |
| 5 | 性能与限制 | SQLite 原有限时等待保持；单活跃槽，不做容量证明 |
| 6 | 安全与合规 | 固定请求，无 token 进入读取 DTO；fence 路径拒绝软链接 |
| 7 | 可观测性 | created/claimed/finished/reconciled 事件及静态错误保持 |
| 8 | 类型与契约 | 严格请求 DTO；claim 与只读 RunView 区分 |
| 9 | 可测试性 | 已有 65 项和独立 2 探针；服务取消/真实容器待下一批 |
| 10 | 工程规范 | 文件快照固定，未混入 UI 或实现外延 |
| 11 | 事务完整性 | 原子 admission、无级联墓碑、旧数据迁移逐字节验证 |
| 12 | 供应链 | uv frozen 安装既有锁，无新增依赖 |

## 5. 整改清单

无阻断整改项。第二批必须继续验证接收 HTTP 取消不能丢 owner、worker 持锁到清理/保存、跨进程 cancel 标志、准备检查、真实 Docker 四场景。

## 6. 架构防腐与长效治理建议

1. 将真实进程暂停/死亡探针保留为持续门禁，避免未来把存活锁替换成过期时间判断。
2. 迁移持续使用含报告与事件的历史库，不仅验证空库或 queued 行；API/服务不得绕过本批 admission 与墓碑机制。

## 7. 审计声明

范围由快照清单限定。API、worker 生命周期、Origin、新 UI 以及真实 Docker 本批未评估，不由本报告取得通过。无生产服务操作、无模型调用、无代码自评。后续变更须增量复核。
