# Agent 修复台

面向 Agent / MCP 工具开发者的工具调用测试与修复工作台。英文仓库名为 `agent-repair-workbench`，Python 包和 CLI 名称保持 `agent-workbench`。

项目先实现可复现的工具调用失败、可核对的证据和固定验收，再引入受约束的诊断、修复、验证 Agent。功能完成情况以迭代台账为准，架构中的组件不代表已经实现。

## 开发入口

1. [文档索引与变更规则](docs/README.md)
2. [产品范围与工程约束](docs/01-constraints.md)
3. [架构与技术决策](docs/02-architecture.md)
4. [优先级与迭代台账](docs/03-roadmap.md)
5. [测试、评估与独立评审](docs/04-quality-gates.md)
6. [P0-01 输入输出契约](docs/05-contract-checker.md)
7. [产品 Agent 目录与新增角色维护指南](docs/09-agent-modules.md)
8. [产品闭环、Agent、工具与测试实施规格](docs/17-agent-tools-testing-plan.md)
9. [P0-05a 角色契约与实际验收](docs/19-p0-05a-delivery.md)

仓库：https://github.com/yduan10/agent-repair-workbench

本地启动后访问 `/docs` 阅读上手与测试说明。当前公开的是开发中的源码快照，模型协作循环与实际补丁验收尚未接通。当前未附项目开源许可证，公开可见不代表已授予通用开源许可；第三方依赖按各自许可证使用。

## 本地运行（macOS / Linux，Python 3.12）

```sh
uv sync --frozen
uv run --frozen agent-workbench check examples/passing.json
uv run --frozen agent-workbench check examples/failing.json
```

第一条检查退出 0；第二条预期退出 1。检查无法完成退出 2。默认限时 5 秒，可用 `--timeout 10` 修改；报告打印到 stdout。`examples` 是合成证据，首版不执行工具或模型。

```sh
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv run --frozen pytest
```

原始 trace 和 `.env` 不提交。分享报告前核对字段路径是否含敏感信息；摘要哈希不是匿名化保证。CLI 不支持 Windows 文件打开语义，Windows 移植需独立验收。

## 产品网页（UI-01）

在项目根目录启动本地 API：

```sh
uv run --frozen uvicorn agent_workbench.api:app --host 127.0.0.1 --port 8030 --no-access-log
```

另开终端启动前端（Node 24）：

```sh
cd frontend
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
NEXT_TELEMETRY_DISABLED=1 npm run start
```

访问 <http://127.0.0.1:3010>。产品首页和七个功能入口已设计；调用检查真实可用，任务总览接入本机运行记录、事件和报告；诊断、修复、回归、记忆和接入按模块标注实际能力。侧栏区分网页可用、CLI可用、待接通与待开发；每个模块首屏展示已完成基础、当前使用入口和后续依赖。全站支持浅色、深色及跟随系统，主题偏好仅保存在本机；[迭代历史](http://127.0.0.1:3010/updates) 保留各阶段的改进和边界。

### 前端测试

在 frontend 目录运行：

```sh
npm run typecheck
npx playwright install chromium
NEXT_TELEMETRY_DISABLED=1 npm run test:e2e
```

测试需要先 production build；Playwright 自动启动未运行的本地服务。已有服务时复用，开发者应先重启到最新构建。本机 Chromium 下载慢时可用已安装的 Chrome：`PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`；CI 使用锁定 Playwright 对应 Chromium。额外运行 `npm run test:runs-live` 可在独立临时数据库与 8031/3011 服务验证运行记录；该命令会按测试端口重新构建，之后启动产品前须用默认环境再次 `npm run build`。CI 已配置这项门禁，本地默认使用 Chrome，CI 通过 `PLAYWRIGHT_CHANNEL=''` 使用安装的 Chromium。浏览器测试包含真实 Python API、数字/BOM保真、错误恢复、预览交互、手机和桌面 axe 检查；并非全用 mock。

[产品界面规格](docs/07-web-workbench.md) · [P0-02 接入设计与测试计划](docs/08-mcp-integration.md)


## 真实 MCP CLI（P0-02）

```sh
uv run --frozen agent-workbench mcp-check --server-config examples/mcp/pass-server.json --case examples/mcp/lookup-case.json
uv run --frozen agent-workbench mcp-check --server-config examples/mcp/failing-server.json --case examples/mcp/lookup-case.json
```

上述使用项目已审核的真实 stdio fixture，预期分别退出 0/1。输入参数失败不会调用工具，调用后超时/断连记录 outcome_unknown，不自动重试。配置不能传入任意 command/args/env；本阶段尚非任意代码沙箱。

公开案例的准备、只读核验和来源见 [实验说明](experiments/public_mcp_case/README.md)。显式准备后：

```sh
uv run --frozen agent-workbench mcp-check --server-config examples/mcp/public-server.json --case examples/mcp/public-case.json
AWB_PUBLIC_CASE=1 uv run --frozen pytest -m public_case
```

公开历史错误的预期 CLI 退出码是 1。MCP 报告只保存版本、摘要与问题路径，标明 SDK 规范化数据和原始 wire 未检查；网页接入能力仍按台账逐项解锁。

## 受控容器执行（P0-03）

前提：本机 Linux Docker daemon（macOS 可用现有 Colima）、固定基础镜像已明确准备。
仅运行项目审核过的合成故障服务；不执行用户上传命令，不开放 Web 容器运行。

```sh
uv run --frozen python containers/p0_03/prepare.py
uv run --frozen agent-workbench sandbox-check --server-config examples/sandbox/pass-server.json --case examples/mcp/lookup-case.json
uv run --frozen agent-workbench sandbox-check --server-config examples/sandbox/lost-response-server.json --case examples/mcp/lookup-case.json
```

正常检查预期退出 0；响应丢失预期退出 2/outcome_unknown，不能自动重试。
容器默认断网、非 root、只读根、0.5 CPU、128MiB 内存、32 个进程、16MiB tmpfs；
无宿主挂载或凭据继承，Docker 日志关闭。原始帧在解码前受字节限制；
报告只保留摘要、错误码、计数和清理确认。运行配置/镜像源码变化需重新显式准备。
镜像取自本次构建 iidfile 并按完整 ID 执行，运行不会自动下载或构建。

正常取消执行精确清理；宿主被 SIGKILL 时容器独立监护按 lifetime 停止（默认45秒，依赖正常内核调度）。
这时没有最终报告；停止容器的元数据可能残留，按已知 run ID 显式检查/清理：

```sh
uv run --frozen agent-workbench sandbox-reap --run-id <UUID>
uv run --frozen agent-workbench sandbox-reap --run-id <UUID> --apply
```

只处理名称/项目标签/run ID 一致的停止容器；不会删除活跃目标。
P0-04 已增加持久运行记录；恢复对账通过下述显式命令进行，不会自动重投工具调用。

```sh
# 默认门禁：没有Docker也可跑；容器测试显示skip，不计容器验收通过
uv run --frozen pytest
# 本机显式准备两类实验后，完整门禁（含真实历史案例与容器故障）
AWB_PUBLIC_CASE=1 AWB_DOCKER_TESTS=1 uv run --frozen pytest
```

[执行规格与故障矩阵](docs/11-controlled-execution.md) · [镜像准备与故障服务](containers/p0_03/README.md)


## 运行记录与恢复（P0-04）

`sandbox-check` 现在先保存执行租约，再启动容器；终态、事件、报告在同一事务提交。
CLI 报告 `record_id` 是持久运行 ID，原 `run_id` 是容器 attempt ID。
本地默认目录 `artifacts/run-store`，可通过 `AWB_STATE_DIR` 为 CLI 和 API 配置同一个独立目录。
不保存原始参数/结果，报告摘要不代表匿名化。网页 `/workspace/tasks` 只读展示这个目录的记录。

```sh
uv run --frozen agent-workbench runs init
uv run --frozen agent-workbench runs list
uv run --frozen agent-workbench runs show <record_id>
uv run --frozen agent-workbench runs report <record_id>
uv run --frozen agent-workbench runs reconcile
uv run --frozen agent-workbench runs prune --days 30
uv run --frozen agent-workbench runs prune --days 30 --apply
```

读取命令不创建库。`reconcile` 只检查过期执行与未确认资源，无法确认完成的调用保持
`outcome_unknown`，不执行重试；恢复事件不能补造缺失的原始报告。
`prune` 默认只预览，只有超期终态、资源确认不存在且报告有效的记录可清理。
没有可靠报告的崩溃记录保留待人工调查。资源清理使用 `sandbox-reap --run-id <attempt_id>`。

迁移当前版本 `0001_run_store`。含数据时禁止降级；活动数据库备份必须使用 SQLite
`Connection.backup()`，不能只复制主数据库而漏掉 WAL。先停止 CLI/API 写入再切换恢复目录；
通过 `AWB_STATE_DIR` 指向恢复副本，执行 `runs list/show/report` 核对记录与摘要后再使用。
备份与恢复的可执行演练见 `tests/test_run_store.py::test_live_wal_backup_refused_downgrade_and_restore`。
完整契约、限制与验收见 [P0-04 说明](docs/14-run-store.md)。

## 协作接口目录（P0-05a）

工具接入与诊断页可通过本机`GET /api/agent-contracts`查看、下载三个角色及五类工具请求的实际JSON schema。接口只读，`runtime_available=false`；契约与权限校验已实现，模型循环、工具handler和分析记录存储仍待P0-05b。详见[冻结规格](docs/18-p0-05a-contracts.md)与[验收记录](docs/19-p0-05a-delivery.md)。
