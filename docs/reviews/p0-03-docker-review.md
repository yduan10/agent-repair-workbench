# 企业代码质量审计报告：P0-03 Docker 控制边界

- **审计对象**：`src/agent_workbench/runner/docker.py`、`tests/test_docker_control.py`；2 文件 / 743 行。
- **版本**：2026-10-13 最终快照，逐文件 SHA-256 见 `p0-03-docker-snapshot.json`。
- **审查目录**：`<review-workspaces>/p0-03-review`。
- **技术栈 / 场景 / 严苛度**：Python 3.12、asyncio/AnyIO、Docker CLI；General SaaS；Mission-Critical。
- **边界**：可信单用户本机 Unix socket Docker daemon，固定镜像、固定合成场景；不认证恶意多租户或远程 daemon。

## 1. 代码质量评估卡

**100 / 100，本批受控本地范围 Pass；未发现未关闭缺陷。**

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0 unresolved
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: scoped local Docker control Pass; not a production certificate
NOT ASSESSED: remote/malicious daemon, hostile multi-tenancy, production deployment (outside scope)
```

独立执行：32 项 Docker 控制单测，与 wire/生命周期/fixture/独立反例共 110 项通过。Ruff、mypy（8 source files）、uv lock --check 通过。未构建镜像或改动共享 tag。

## 2. 生产事故风险推演

none 本批确认 P0/P1。原先发现的 fixture 构建来源错绑及 transport 背压读取停止分别由第一、第二批报告跟踪，均已修复复审。本批核查 daemon 故障、模糊创建、清理失败、活跃目标误删等路径；故障发生时拒判而非成功。

## 3. 详细审计明细

### P0

none。

### P1

none。

### P2

none 未关闭。接线期间 `stdout_total_flood` / `pid_limit` 枚举遗漏已即时反馈并确认最终 DockerControl.SCENARIOS 与 SandboxConfig 一致，真实目标场景得以执行。

### P3

none。

### 证据与已核对行为

- `connect` 固定 Docker 可执行文件绝对路径，只接受实际存在的本地 Unix socket；命令固定 `--host`，不会因中途默认 context 变化转向另一端点。宿主秘密和 DOCKER_HOST 不继承；HOME仅给宿主Docker CLI定位上下文，不传容器。
- Docker 控制命令各有 5 秒截止，stdout 64KiB/stderr 16KiB解析前上限；失败只交固定代码，子 CLI 在finally内回收。未知命令成功没有被当作容器成功。
- create 仅允许规范 UUID、完整镜像ID、固定scenario、严格seed/lifetime。ACK窗口有界屏蔽协作取消；失败或格式不明统一 create_unconfirmed，上层不因瞬时未查到容器误报清理完成。
- verify 在启动前检查 Image、User、Entrypoint/Cmd、完整环境字段、无Volumes/Healthcheck、无Bind/Devices/CapAdd，以及 CPU/内存/Swap/PID、断网、只读、cap-drop/no-new-privileges、tmpfs、log-driver none、restart、命名空间；不只验证拼出的命令字符串。
- cleanup 以精确 name/run UUID/项目标签匹配后删完整ID，再确认不存在。daemon 错误不返回 absent。
- reap 仅对明确 exited/dead 的本项目目标操作，活跃及 created 状态不删。实际删除不用 force，避免检查后并发start时误杀运行任务。
- 本 reviewer 已读真实 `test_sandbox_docker.py`：测试只kill自己Popen的宿主PID，并只cleanup自己UUID；验证PID配额EAGAIN、副作用计数为1、SIGTERM unknown+removed、SIGKILL watchdog退出124/Pid0、精确停止残留reap。主 Agent 报告18项真实Docker与全量回归通过；这些不是本 reviewer 亲自重复全部执行的声明。

### Reviewer 独立真实 CLI 验收

固定镜像 `sha256:3c5b0613294b2fb3cfc63817085fcae590676c2df5c482f18334929fd78da766`；来源摘要 `5b5031e5ffb18daf1161e6fd867551f31f3db0f582c4da4f6ab44af219443cd3`；运行前 `verified_image()` 匹配完整本地源码。每次新建独立UUID，无共享tag构建。

| 场景 | CLI退出 | execution.error | cleanup | 耗时秒 |
|---|---|---|---|---|
| pass | 0 | null | removed | 1.49 |
| duplicate_result | 2 | duplicate_response_id | removed | 1.02 |
| stdout_flood | 2 | frame_limit_exceeded | removed | 1.15 |
| stdout_total_flood | 2 | stdout_limit_exceeded | removed | 1.06 |
| stderr_flood | 2 | stderr_limit_exceeded | removed | 1.06 |

随后另行 inspect 本 reviewer 五个 UUID，输出 `independently_confirmed_absent: 5 own run UUIDs`。CLI stderr均为空。局部产物在独立审查目录 `artifacts/review-p0-03/`，不提交原始调用值。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构与边界 | 本机控制/协议/业务报告分离，无未闭项 |
| 2 | SOLID / 设计 | 固定profile集中权限，无任意argv入口 |
| 3 | 并发与资源 | ACK屏蔽有界；cleanup/reap并发语义保守；独立5次回收核验 |
| 4 | 容错 | timeout/daemon失败/不确定创建保持拒判 |
| 5 | 性能 | 控制CLI字节/时间有界；不宣称吞吐或累计CPU秒保证 |
| 6 | 安全与合规 | 实际容器策略验收；无Docker日志、宿主挂载或容器凭据传递 |
| 7 | 可观测性 | 固定错误码，来源/限额/清理证据分离 |
| 8 | 类型契约 | mypy通过；UUID/image/scenario有边界 |
| 9 | 可测试性 | 32控制单测与5次独立CLI；故障测试有特定oracle |
| 10 | 工程规范 | 独立目录、分批摘要、静态检查通过 |
| 11 | 数据完整性 | unknown不推断无副作用，不自动重试；清理失败不得成功 |
| 12 | 依赖治理 | 固定image ID与source hash；构建来源修复见fixture报告 |

## 5. 整改清单

none 未关闭。P003-F01/F02/R01 均已修复复审，分别见 fixture/runner 报告。

## 6. 架构防腐与长效治理建议

1. 每次增加scenario同步配置/fixture/控制枚举与真实断言，避免入口存在却无法执行目标故障。
2. 继续区分“可查到不存在”与“daemon不可达”；把这一负向用例保留为cleanup门禁。
3. P0-04实现持久状态时保留未知创建/运行语义，不将进程退出推断为外部副作用撤销。

## 7. 审计声明

仅适用于本地审核fixture、固定镜像与对应摘要。无强多租户隔离、远端daemon、任意代码托管、生产部署承诺。未构建镜像、未修改实现，真实运行只创建/回收本 reviewer 自己五个UUID的容器。后续源码或锁定镜像变化须增量复审。
