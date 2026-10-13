# 企业代码质量审计报告：P0-03 runner 第二批最终复审

- **范围**：runner 的 `__init__.py/models.py/transport.py/service.py/cli.py`，入口 `cli.py` / `mcp_models.py` 增量，`tests/test_sandbox_wire.py`。
- **版本**：2026-10-13 工作副本，10 文件摘要见 `p0-03-runner-snapshot.json`。
- **目录**：`<review-workspaces>/p0-03-review`。
- **技术栈**：Python 3.12、AnyIO、MCP SDK 2.3.0、Pydantic。
- **场景/严格度**：General SaaS / Mission-Critical。
- **审计方式**：只读实现、独立 wire 单测与纯内存传输反例，最后追加5项固定镜像真实CLI。不构建镜像，不操作其他任务容器。

## 1. 代码质量评估卡

**100 / 100，本批受控本地 runner 范围 Pass；发现的 P003-R01 已修复并独立复审关闭。**

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 unresolved; P003-R01 fixed and verified
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped trusted-local runner Pass; not production certification
NOT ASSESSED: hostile multi-tenant / production deployment (outside scope); DockerControl separate report
```

独立执行 `uv run --frozen pytest -q tests/test_sandbox_wire.py`：

```text
................                                                         [100%]
```

共 16 项通过。覆盖分块、重复/未知 ID、ID 类型区别、非法 JSON/重复键、服务器主动请求拒绝、无换行单帧限制、合法通知总字节限制、stderr 与配置边界。

## 2. 生产事故风险推演

本批发现并修复 P003-R01：背压终止读流可能令持续写入的 attach 与容器清理停滞；修复和重现见下文。DockerControl 已在单独报告复审；不把“daemon暂时查不到”视为创建一定未发生。

## 3. 详细审计明细

### P0

none。

### P1 — P003-R01：背压后退出 stdout 读者（已修复关闭）

- **原位置**：transport.py 的 stdout `incoming.send_nowait` WouldBlock 分支，抛 WireFailure 进入外层 except 后退出读取。
- **维度**：并发/资源安全。**置信度**：confirmed。
- **场景**：SDK接收队列16槽满，stdout读者退出，持续输出的工具使Docker attach背压；rm无法及时完成，出现cleanup_unconfirmed。主 Agent此前真实发现的限额读取停止问题具有相同机制。
- **独立复现**：内存管道填满16槽后继续发送，旧版输出 `inbound_backpressure / producer_blocked_after_error:true / stdout_read_calls:17`。
- **最小修复**：WouldBlock分支改为 `await fail("inbound_backpressure"); break`，留在raw读取循环；state.error存在时继续丢弃后续字节，不再解析或保存。
- **复审**：固定回归先得到相同背压错误，再证明后续100帧可继续输送，不阻塞生产者；`tests/test_transport_drain_regression.py`通过。真实重复响应及三种输出上限的CLI均确认容器removed。
- **负责人/状态**：`/root`，2026-10-13 fixed / independently verified。

### P2

none 新增。本文件不覆盖第一批 fixture 的 P003-F02 修复状态。

### P3

none。

### 已验证的重要路径

1. stdout/stderr 原始字节先计量；无换行缓冲在帧上限拒绝，读取 chunk 为 4096 字节；JSON 错误不带原始值跨边界。
2. JSON-RPC 关联键包括 ID 类型与值；未知、重复 response 及 server request 不交给 SDK 解释为成功；同一 chunk 内合法+重复响应整批拒绝。
3. 读端关闭后继续验证尾部帧；独立纯内存 Process 替身先传成功 response，再关闭 SDK receive 端并发送重复 response，结果如下。
4. stderr 限额可结束 incoming stream，唤醒 SDK 响应等待，不依赖 timeout 才退出；独立内存流验证如下。
5. service 在 MCP 完成后进行有限排水与容器状态检查；清理期间保留读者。最终 `execution.error` 会调用 `_Run.failure`，将已收到结果的报告转为 inconclusive；`SandboxReport.exit_code` 在 execution error/cleanup unconfirmed 时固定 2。
6. 已发出调用但未取得结果时保留 outcome_unknown；清理移除容器不改变这一事实。无自动重试。
7. 控制配置不接受 argv/env/path；CLI 暂停 SDK logging 并在返回前恢复，避免已知 SDK 原值日志。未将 Python 嵌入式 API 当公网服务评审。

独立纯内存反例输出：

```json
{"case":"duplicate_after_sdk_read_closed","error":"duplicate_response_id"}
{"case":"stderr_limit_wakes_sdk_waiter","error":"stderr_limit_exceeded","bytes":69632}
```

stderr 69632 是 64KiB 上限再读一个 4096 字节 chunk 后拒绝的计数，不是允许缓存无限数据。

### 初审提出的必要验收（最终证据见后文）

- DockerControl.create 的 ACK/cancel/timeout 状态与 create_unconfirmed 一致；即使暂未找到容器，也不能将模糊创建当已回收。
- attach CLI 进程与实际容器均精确清理；所有 Docker 控制操作有界，清理失败报告而非抛原始异常或错误成功。
- 检查 valid result 后的重复响应/坏帧、stderr 洪泛在真实管道调度下也不误报 passed。
- OOM、CPU、PID、宿主 SIGTERM/SIGKILL、setsid 孙进程和停止残留 reap 实际运行；不以本批纯内存测试代替。
- 最终快照需重新跑静态与既有回归。本阶段 DockerControl 文件尚未进入审查目录，未声明服务整体验证通过。


### 最终联动复审证据

- **F01 关闭**：prepare 使用独立临时 `--iidfile`，输出路径在 build context 外；以本次不可变 ID inspect，并核对精确 ENV、无 VOLUME、ENTRYPOINT、USER、WorkingDir；缺失/非法 iid 和 identity mismatch 拒绝。44 项准备/fixture 单测通过，包含并发 retag 反例，manifest 不再取共享 tag 的 ID。
- **F02 关闭**：无换行洪泛与合法通知总量洪泛分开；独立截获首个 write 验证两者格式。真实产品 CLI 分别触发 `frame_limit_exceeded` / `stdout_limit_exceeded` 并清理确认，不再把非法 JSON 当限额证据。
- policy_probe 已改为对归属 65532 的 server.py 进行不截断、不写入的写打开，并区分 EROFS 与 EACCES。独立两项回归通过。
- PID fixture 改为 `os.fork` 写时复制，避免 Python 新解释器内存耗尽先于 PID 上限；EAGAIN marker 和释放少量槽位逻辑已读。主 Agent 报告真实 EAGAIN=11、SIGKILL watchdog=8 秒/exit124/Pid0 的验收；本 reviewer 阅读真实测试代码，未独立重复故障宿主 kill。
- 主 Agent 报告完整 274 项（含 18 Docker）通过，再合入 reviewer drain 测试为 275 项；这些是主集成证据，不能表述为本 reviewer 亲跑全部 275。
- 本 reviewer 亲跑本批与联动单元总计 **110 项**，另亲跑 5 项真实 CLI：pass=0；duplicate_result/stdout_flood/stdout_total_flood/stderr_flood=2，错误代码正确，cleanup 均 removed。随后逐个查询自身 UUID，确认 5 容器均不存在。
- 固定执行 image ID：`sha256:3c5b0613294b2fb3cfc63817085fcae590676c2df5c482f18334929fd78da766`；source SHA：`5b5031e5ffb18daf1161e6fd867551f31f3db0f582c4da4f6ab44af219443cd3`。
- 最后追加5项manifest/source/symlink篡改测试已读并独立运行，生命周期文件13项通过；加上前述105项，其中5项为新增，独立去重单元总数110。
- Ruff、mypy（8 source files）、uv lock --check 均通过。本地原始输出仅在 reviewer 独立 `artifacts/review-p0-03/`，报告未包含调用值或原始 stderr。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | wire/service/CLI 分离，复用确定性 checker，无新确认缺陷 |
| 2 | SOLID / 设计 | 本批边界清楚，无额外框架要求 |
| 3 | 并发与资源安全 | wire 唤醒/背压已查；Docker生命周期见第三批报告 |
| 4 | 容错 | 安全码、unknown、cleanup否决成功路径已查 |
| 5 | 性能 | 原始输入限额与固定stream容量已查；资源配额inspect已查，主集成故障证据已核对 |
| 6 | 安全与合规 | 无原值报告，CLI日志抑制；只认证受控本地范围 |
| 7 | 可观测性 | 错误码/字节数/cleanup状态明确 |
| 8 | 类型与契约 | 严格配置和报告；mypy通过 |
| 9 | 可测试性 | 16 单测与两项独立内存流反例通过 |
| 10 | 工程规范 | 限定批次；Ruff/mypy/lock通过 |
| 11 | 数据完整性 | 成功结果被尾部错误否决；未知副作用不重试 |
| 12 | 依赖治理 | 沿用锁定SDK，Docker控制边界见第三批报告 |

## 5. 整改清单

P003-R01：`/root`负责，2026-10-13已修复并复审。第一批F01/F02也已关闭，分别见fixture报告。无未闭整改项。

## 6. 架构防腐与长效治理建议

1. 永久保留“成功结果后故障”验收，防止后续重构在拿到结果时提前发布 passed；成本为真实管道两项反例。
2. 清理结果与业务结果保持独立字段，但任一无法确认必须阻止 exit0；避免异常处理抹去已执行事实。
3. SDK升级同时跑真实尾部响应与取消测试；其 stream 关闭时序不能仅靠静态类型保证。

## 7. 审计声明

本报告覆盖摘要清单中十文件；DockerControl 在独立第三批报告中审查。最终运行了自己5个UUID的容器，未构建镜像、未触碰其他任务容器、未修改实现。无未关闭缺陷；后续改动须增量复审。恶意多租户与生产部署不在本地阶段结论中。
