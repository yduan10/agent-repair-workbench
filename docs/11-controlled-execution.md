# P0-03：受控执行与故障注入

2026-10-13 / Feature P0。前置P0-02完成；本规格经设计预审后实施，最终状态见03台账。

## 目标与边界

在可信单用户、本机Docker daemon上，运行审核过的固定fixture，给MCP调用增加执行隔离、字节级输出边界和可核实的清理结果。不是任意上传代码托管服务；不开放网页命令输入，不安装模型、不接入数据库或自动恢复。

产品代码放 `runner/`，与 `agents/<role>/` 和MCP协议适配独立。容器fixture放 `containers/p0_03/`，标准库实现最小MCP wire以注入故障，产品客户端仍使用锁定官方SDK和既有确定性checker。合成故障不能计入真实历史故障统计。

## 容器与镜像

- 显式 `prepare.py` 构建本项目专用镜像；基础镜像按官方digest固定，本机缺镜像时拒绝，不隐式pull。
- build禁网络，输入仅Dockerfile和审核脚本，生成包含source摘要、完整image ID、base digest的本地产物。每次运行核对来源摘要和镜像身份；实际执行用完整image ID，不靠可变tag。
- `--network none --read-only --user 65532:65532 --cap-drop ALL --security-opt no-new-privileges --cpus 0.5 --memory 128m --memory-swap 128m --pids-limit 32 --log-driver none --init`。
- 仅16MiB `/tmp` tmpfs，可写副作用计数；无宿主bind mount、volume、Docker socket、HOME、凭据、可写验收目录；不继承宿主环境到容器；restart=no。
- 不只验证argv，还要在start前inspect实际Image/User/HostConfig/Mounts；运行中通过policy_probe核对cgroup/uid/只读/网络等。
- CPU是可用核配额，不是累计CPU时间。内存/tmpfs/进程配额包含监护和工具进程；不保证恶意租户或daemon故障下的强隔离。

## 生命周期与预算

1. 严格配置，只接受固定profile/scenario/seed/lifetime，不接受shell/路径/环境注入。
2. 预分配run UUID和唯一容器name，绑定项目label及run ID；创建请求开始后即记录定位信息，避免只靠成功返回的ID才能清理。
3. create/inspect/start/attach等Docker控制命令均有超时；create正常阶段短暂屏蔽协作取消等待ACK，超时或失联标结果未知，不能因为即时inspect未找到就认定永远不会创建。
4. 共享30秒执行deadline，MCP每阶段最多5秒。正常和取消均在finally中关闭transport，按精确目标rm -f并确认不存在。清理另有有界预算；未确认清理不得exit0。
5. 容器内独立监护进程从启动起设置硬截止，默认45秒，测试允许5～45秒；工具worker不能取消它。宿主被SIGKILL时，监护退出触发容器PID命名空间结束，包含setsid孙进程。该时长依赖正常内核调度，不是daemon故障下的实时保证。
6. 主机被SIGKILL不能输出最终报告；容器停止后的元数据残留通过显式 `sandbox-reap --run-id UUID` 查看，`--apply`清理。只处理本项目准确label/name匹配且已停止的容器；活跃目标绝不由reap删除。运行状态持久化/恢复对账留P0-04。

## 输送与结果语义

在UTF-8/JSON解码前，按原始bytes累计stdout≤2MiB、单帧≤1MiB、stderr≤64KiB。并发排水；跨chunk、无换行、异常EOF、洪泛、背压都有限制。禁止原始stdout/stderr写报告或Docker日志。

使用官方SessionMessage/ClientSession；原始帧先过严格JSON及关联检查，拒绝重复response ID、未知response ID和未支持的server请求。有效结果后紧接重复/坏帧也要影响最终报告，不能后台吞掉。正常结果后短暂排水、直至本次session关闭；这只检查有界可观察会话，不能证明任意未来都不会发第二条结果。

- 工具isError、协议错误、执行器资源失败分别记录。
- call已发出但无可靠终态：outcome_unknown，不自动重试；停止容器不表示没有副作用。
- 已取得结果但输送/资源/清理失败：保留收到结果的事实，整次检查拒判，禁止成功退出。
- 报告包含执行ID、镜像/source摘要、seed/scenario、字节计数和固定错误码、资源策略和清理确认。原始参数/结果/异常不外显。

## 故障矩阵和验收

| 场景 | 必须证明 |
|---|---|
| pass / policy_probe | 真握手/调用；实际限制符合策略；清理后容器不存在 |
| tool_error | 业务失败与传输错误分开 |
| timeout / response_lost | 副作用已发生却无返回时unknown，无重试 |
| duplicate_result | 同一响应重复不误报通过 |
| crash_before_call / during / before_result | 调用前与调用后失败分类正确、无挂死 |
| stdout/stderr flood | 解析前字节上限、无原值泄漏、容器回收 |
| spawn_child / 宿主SIGTERM | setsid且忽略TERM的孙进程随容器消失 |
| 宿主SIGKILL | 独立监护终止容器进程树；精确reap处理停止残留 |
| OOM / cpu_spin / PID限制 | 实际配额可观察，资源失败不报成功 |
| 取消于create前/ACK间/start前 | 目标可定位；未知创建不谎报清理成功 |
| daemon失败 / rm失败 | cleanup_unconfirmed，禁止exit0 |
| 配置/镜像篡改 | 启动前拒绝，不执行任意命令 |

默认CI跑无Docker的单元/字节流边界测试；显式 `AWB_DOCKER_TESTS=1` 开真实容器门禁。Docker缺失不得把skip算容器验收通过。保留156项既有验收（公开案例需独立准备），前端同步开发/完成状态及历史；独立review按实现、fixture、UI分批，修复后复审。

官方依据：[资源限制](https://docs.docker.com/engine/containers/resource_constraints/)、[容器参数](https://docs.docker.com/reference/cli/docker/container/run/)、[日志配置](https://docs.docker.com/engine/logging/configure/)。锁定范围以实际Docker版本、inspect和运行测试为准。

## 2026-10-13 验收记录

- 显式镜像准备成功：`artifacts/p0-03-image.json`，image `sha256:3c5b0613294b2fb3cfc63817085fcae590676c2df5c482f18334929fd78da766`，source `5b5031e5ffb18daf1161e6fd867551f31f3db0f582c4da4f6ab44af219443cd3`。并发构建产物通过iidfile绑定，tag不参与运行身份。
- `AWB_PUBLIC_CASE=1 AWB_DOCKER_TESTS=1 uv run --frozen pytest`：**284 passed / 67.47s，0 skipped**。包含原156项、128项新增测试；新增含18项真实Docker验收，其余是配置/生命周期/输送/准备与回归单测。pytest启用importlib发现，两个test_prepare.py均被收集。
- 真容器矩阵：16个场景全部达到各自预期；stdout无换行、合法通知累计与stderr洪泛分别断言frame/stdout/stderr限额。PID探针实际读到EAGAIN，策略schema核实UID/EROFS/loopback/合成secret缺失及cgroup值；OOM/CPU/子进程取消不误报通过。
- 宿主SIGTERM：unknown、cleanup=removed；宿主SIGKILL：测试lifetime=8s的独立监护退出124、容器Pid=0，精确dry-run/reap删除停止元数据。没有把SIGKILL当作可输出最终报告的正常取消。
- 实际CLI：`examples/sandbox/pass-server.json`退出0/completed；`lost-response-server.json`退出2/outcome_unknown；两者cleanup=removed且stderr为空。元数据报告在忽略的artifacts目录。
- `uv run --frozen ruff check .`、`ruff format --check .`、`mypy`、`uv lock --check`通过。
- 前端production build/typecheck通过；`PLAYWRIGHT_CHANNEL=chrome NEXT_TELEMETRY_DISABLED=1 npm run test:e2e`：**18 passed / 24.8s**。三态主题、降低动效、历史保留、桌面/手机及真实API路径通过。
- 独立评审按[fixture](reviews/p0-03-fixture-review.md)、[runner](reviews/p0-03-runner-review.md)、[Docker控制](reviews/p0-03-docker-review.md)、[UI](reviews/P0-03-ui-review.md)分批；iidfile身份串用、stdout故障设计、背压后停止排水与旧状态断言已修复/复审。后端reviewer独立执行5个容器CLI场景并逐UUID核对不存在；无未闭Defect P0/P1。

当前仅认证本机已审核fixture执行。没有新增模型、产品Agent实现、任意代码上传或网页任务调度。下一依赖是P0-04运行状态、产物与恢复对账，不能把容器清理等同于运行状态持久化。
