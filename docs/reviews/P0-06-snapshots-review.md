# P0-06 B1a 候选快照独立代码评审

- 审计对象：`src/agent_workbench/candidates/{__init__,contracts,snapshots}.py`、`tests/test_candidate_snapshots.py`；追加独立反例 `tests/test_candidate_snapshots_review.py`。
- 版本：当前工作树，逐文件 SHA-256 见文末。
- 技术栈：Python 3.12、Pydantic、POSIX 文件描述符、macOS / Linux 原子不覆盖重命名。
- 方法：auditing-enterprise-code-quality；General SaaS / Mission-Critical。
- 时间：2026-10-14；评审者 final_review，独立于实现者 code_review_m0；未修改生产实现。

## 1. 代码质量评估卡

**Pass，100/100，仅放行 B1a 快照库。** 没有确认的 Defect P0/P1/P2/P3。此库不会执行候选或宣布修复通过；两候选上限、请求去重、数据库预登记与工具权限由后续调用层实现，尚不在本批交付中。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (B1a snapshot library only)
NOT ASSESSED: complete Linux suite; future DB/tool/API/execution integrations
```

未评估项不阻断这次纯库增量；不能据此把 B1 持久化、B2 oracle 或父 P0-06 标记完成。Linux 实证限于实际原子发布函数，不是整个模块的 Linux 验收。

## 2. 生产事故风险推演

无待修 P0/P1。针对本范围承重失败场景已核对：

- 两个进程发布同一 ID：只允许一个完整快照可见，另一方返回冲突；已有空目录也不能覆盖。
- 发布前写入或 fsync 失败：基线不变，局部 staging 清理；rename 后目录 fsync 失败：保留已发布内容并返回 `SNAPSHOT_COMMIT_UNKNOWN`，不自动重复应用。
- 读取前或读取中内容变化、软链接、硬链接、FIFO、额外文件、权限变化：拒绝核验与 diff，不把旧摘要作为新内容依据。

本机同 UID 所有者是明确的信任边界。只读模式与摘要不构成对恶意本机管理员的隔离保证；后续执行器必须在执行前后重新核验。

## 3. 详细审计明细与实证

**P0/P1/P2/P3：none。**

检查结果：

1. 原始来源绑定完整文件 SHA、manifest SHA、固定路径与 107–110 行范围。替换前后范围外字节一致，完整 AST 保持函数签名、装饰器及函数外节点；候选均从原基线生成。
2. 公开 DTO 不含磁盘根，不含 `candidate_verified`。`model_copy` 绕过校验后仍在入口重新校验；私有 handle 不能把合法引用重定向至另一目录。
3. 目录逐级 `O_NOFOLLOW`，文件需为单链接常规文件；有字节上限、文件及目录身份前后校验。文件与目录 fsync 后才不覆盖发布。平台缺失对应原语时失败关闭。
4. diff 仅由已核验、固定公开案例源码及授权函数体候选产生，路径固定，结果有界；生成后再次核验。没有额外私有文件读取入口。静态 AST 校验不宣称语义正确。
5. 错误边界使用固定代码，不传播底层含路径的异常文本；当前没有新增网络依赖、执行命令或模型调用。

### macOS 独立实跑

```sh
uv run --frozen pytest tests/test_candidate_snapshots.py tests/test_candidate_snapshots_review.py -o addopts='' -q
uv run --frozen ruff check src/agent_workbench/candidates tests/test_candidate_snapshots.py tests/test_candidate_snapshots_review.py
uv run --frozen ruff format --check src/agent_workbench/candidates tests/test_candidate_snapshots.py tests/test_candidate_snapshots_review.py
uv run --frozen mypy src/agent_workbench/candidates
```

实际输出：

```text
53 passed in 0.89s
All checks passed!
5 files already formatted
Success: no issues found in 3 source files
```

46 个作者用例由评审者重新执行；新增 7 个独立用例覆盖双进程真实发布冲突、五种绕构造的非法引用、正文保持惰性及私有句柄重定向。探针不在宿主执行候选正文。

### Linux 独立 syscall 验证

使用已存在 Python 3.12 slim-bookworm 镜像 ID `sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134`，源码目录只读挂载到 `/review`；断网、只读根、UID 65532、cap-drop ALL、no-new-privileges、128 MiB / 32 PID / 16 MiB tmpfs。未 pull、安装依赖或传入凭据。

评审 harness 从实际 `snapshots.py` AST 提取 `_rename_exclusive`，以同名标准库和最小固定代码异常执行该函数；独立构造普通目录发布、已存在空目录冲突及两个 OS 进程竞争同一目标。只执行已审核的发布函数，未执行候选程序。退出 0，实际输出：

```text
Linux production renameat2: publish, empty-directory no-replace, multiprocess single-winner passed
```

这项测试确认 Linux 原语与 flag 的实际行为；完整来源/DTO/故障测试由上面的 macOS 53 项覆盖，未声称 Linux 全套通过。

## 4. 维度覆盖声明

| # | 维度 | 发现数 | 证据与范围 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 只做快照与安全 diff，无执行/修复结论 |
| 2 | SOLID 与设计 | 0 | DTO、来源核验、发布与读取职责可辨识 |
| 3 | 并发与资源 | 0 | fd 关闭、真实进程冲突、不覆盖原语 |
| 4 | 容错 | 0 | 磁盘注入、unknown 保留、无自动重做 |
| 5 | 性能与限额 | 0 | 源码 128 KiB、片段 8 KiB、diff 64 KiB 上限 |
| 6 | 安全与合规 | 0 | 无候选执行、no-follow、固定公开源码范围 |
| 7 | 可观测性 | 0 | 固定失败码；持久事件属于下一批调用层 |
| 8 | 类型与契约 | 0 | 严格 DTO、入口再校验、mypy 通过 |
| 9 | 可测试性 | 0 | 正反例、故障、跨进程及跨平台 syscall 实证 |
| 10 | 工程规范 | 0 | 独立评审、格式/静态门禁、明确阶段边界 |
| 11 | 数据与事务 | 0 | 不把 FS 与 DB 当同事务；发布未知保留 |
| 12 | 依赖治理 | 0 | 无新增包；只使用已有 libc / 标准库 / 锁依赖 |

## 5. 整改清单

none。没有待修阻断项或豁免。

## 6. 架构防腐与长效治理建议

1. 后续持久化调用者必须先登记请求摘要、候选序号和发布身份，再调用本库；以崩溃注入验证 unknown 对账，不自行重试。此为 B1 后续已规划门禁，防止本库的局部原子性被误当成端到端幂等。
2. B2 使用私有快照根时仍执行前后核验，下载经 `diff` 重新核验；不可仅凭缓存引用沿用 verified。此为后续集成门禁，不能由本次静态库测试代替。

## 7. 审计声明

生产实现只读；评审者仅追加独立测试与报告。通过不代表候选语义正确、模型效果改善或完整修复流水线可用。完整 Linux 套件和数据库/执行/UI 集成未评估，分别留给后续批次。无豁免、无 suspected 发现。下列源码/测试变动后需增量复核。

```text
d36a41580e4e94377529b7c25932507be19e859ee971b0aa74cf936c2c5ca7e4  src/agent_workbench/candidates/__init__.py
34382d3d2ff4c8cd4e1ee06ae6252cb3793b872e9f460f050152744cc4d92e5c  src/agent_workbench/candidates/contracts.py
8f9c5b292db69684e26785738a8ada2ded0d6121339fdc5b4b35de2c4f245baa  src/agent_workbench/candidates/snapshots.py
df469c97ce9a5e06dce328ec7792d447a5f787730a26d54a5e48452eb37c72e2  tests/test_candidate_snapshots.py
8acbd9d30449ecf34b17fea9cfc99436ab0ecdd48ac97e939fc6218f0b4b7d89  tests/test_candidate_snapshots_review.py
```
