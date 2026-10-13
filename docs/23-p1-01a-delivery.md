# P1-01a 实施与验收记录

设计始于 2026-10-13，交付于 2026-10-14。状态：done。约束与验收矩阵见[22](22-web-reproduction.md)，设计预审见[报告](reviews/P1-01a-design-review.md)。

## 1. 当前完成到哪里

| 阶段 | 已完成 | 尚未完成 |
|---|---|---|
| M0 | 调用契约检查、证据与 CLI | — |
| M1 | 真实 MCP stdio、受控 Docker 故障复现、持久运行与恢复对账 | 任意外部工具接入不在本批范围 |
| M2 | 三角色输出、工具请求、权限与状态契约 | P0-05b 模型/工具运行、预算循环与摘要持久化；P0-06 候选补丁和独立验收 |
| 网页 | 检查、运行操作、证据报告、站内文档、主题和完整开发历史 | 模型诊断、补丁审批、项目经验记忆 |

P1-01a 是应用户要求提前交付的固定场景入口。父任务 P1-01 保持 planned，P0-05 保持 in_progress。没有用此处的执行测试声称 Agent 诊断准确率或自动修复成功率。

## 2. 本批功能

- 任务页可选择正常调用、工具错误、调用超时、响应丢失，在本机真实 Docker 中运行固定 lookup 用例。
- 开始、请求停止、刷新、筛选历史、查看真实状态事件、核验报告摘要、下载原字节报告均有实际接口。
- 命令区可下载四种固定配置、复制 CLI 命令；技术 ID、版本、租约等折叠。展示结构化执行事件，不模拟宿主终端。
- 写请求使用持久 ID 去重；刷新或请求断线后仅查询原请求。取消应答不是终态，已发出的调用仍可能结果未知。
- 接收/claim 同事务，跨进程 owner 存活锁贯穿执行到清理与保存。旧 owner 暂停时，租约过期不能让第二个执行者穿越；安全证据不完整则保留槽。
- 0002 迁移增加 Web 请求记录与去重墓碑。旧记录被清理后相同请求返回 410，不创建第二次执行。

## 3. 验证命令与实际证据

### 后端

```sh
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv lock --check
# 需已显式准备固定镜像；不触发镜像构建/拉取
AWB_DOCKER_TESTS=1 uv run --frozen pytest tests/test_web_reproductions_docker.py
```

- 主目录整合默认回归 448 项通过、27 项显式跳过；随后合入独立 reviewer 的 6 项反例并单独全部通过。27 项是需要额外准备的门禁，不能算执行成功。
- 新增四种真实 Docker 场景全部通过：pass → succeeded，tool_error → failed，timeout/response_lost → outcome_unknown；报告关联、清理 removed、槽释放与同 ID 不重跑都核验。
- Ruff、格式、mypy（48 个生产源文件）、依赖锁检查通过。
- 独立存储评审覆盖 65 项回归、2 项真实进程/迁移反例，最终增量 15 项复核；服务评审 45 项通过（39 项已有、6 项独立），两批互相独立于实现者。各组有重叠，不合计成额外总数。

### 前端与真实链路

- 前端独立 production build 和 23 项浏览器测试通过：四场景选择、重复点击、响应丢失仅查询、离页、取消失败、坏 SHA/关联、配置下载/命令、四种主题/视口的 axe 与键盘操作。
- 整合完整浏览器首轮 72 passed / 2 skipped / 1 failed；唯一失败是旧能力文案断言仍要求“网页尚未接入”。更新为固定场景已开放、自定义接入未开放，并在后续真实 SQLite/API 的 21 项套件中复核通过。没有删除断言或放宽实际能力边界。
- 隔离端口 3013/8033、临时状态库执行 `reproductions-live.spec.ts`：**1 passed（9.8 秒）**。真实浏览器开始 → HTTP 接收 → Docker 正常运行 → 报告核验 → 第二次超时任务 → 请求停止 → 实际终态与清理验证。
- `npm run test:runs-live`：**21 passed（22.6 秒）**，使用独立临时 SQLite 与 3011/8031，包含原始报告下载及断网恢复。此套件不使用 Docker，不冒充实际容器验证。
- 普通 UI 套件中的真实 SQLite / Docker 专用用例默认跳过，分别由上述显式门禁执行。

W10 的真实正常/取消链路采用实际 API 和容器；双击、断线、迟到响应等故障使用浏览器路由故障注入，服务端请求中断另由独立 ASGI 反例验证。不同证据承担不同检查范围。

### 复跑真实网页门禁

先完成仓库依赖与固定镜像准备，并确保专用端口空闲。在项目根目录执行（测试用隔离状态，不写正常产品数据库）：

```sh
awb_test_root=$(mktemp -d /tmp/awb-web-e2e-XXXXXX)
export AWB_STATE_DIR="$awb_test_root/state"
export AWB_FRONTEND_PORT=3013 AWB_API_PORT=8033 PW_PORT=3013
uv run --frozen agent-workbench runs init
npm --prefix frontend run build
(cd frontend && CI=1 AWB_WEB_DOCKER_E2E=1 npx playwright test tests/reproductions-live.spec.ts)
# 本机使用已安装 Chrome 时，加 PLAYWRIGHT_CHANNEL=chrome
# 测试后保留目录可人工检查；不把产物提交到仓库。
unset AWB_STATE_DIR AWB_FRONTEND_PORT AWB_API_PORT PW_PORT
# 回到正常产品端口前，重新生成默认代理配置
npm --prefix frontend run build
```

## 4. 本机迁移与准备

已有库先用 SQLite `Connection.backup()` 一致性备份并验证完整性，停止 API 写入后显式 `runs init` 升级。升级后旧 **2 条 runs、2 条 attempts、6 条 events、2 份原始报告**逐表摘要一致，`integrity_check=ok`。没有靠直接复制 WAL 中的主库做备份。新版 API 已重启。

所有新增开发测试使用独立临时状态目录，不将测试数量或测试结果灌入正常任务列表。网页准备检查不会初始化数据库、构建或下载镜像。

## 5. 独立评审与范围

| 批次 | 覆盖 | 结果与报告 |
|---|---|---|
| 设计 | 接收边界、故障窗口、资源所有权 | [Pass](reviews/P1-01a-design-review.md)，D01 通过同锁对账设计关闭 |
| 存储与锁 | W02/03/04/06/07、迁移保真与进程暂停/死亡 | [Pass](reviews/P1-01a-store-review.md) |
| 执行服务/API | W01/03/05/06/08、取消/断线/停服/敏感信息 | [Pass](reviews/P1-01a-service-api-review.md) |
| 前端 | W10/11/12、真实状态消费与报告核验 | [Pass](reviews/P1-01a-ui-review.md) |

各报告附冻结源码摘要；前端 mock 测试不替代真实门禁。无未闭 Defect P0/P1/P2。本批没有新增模型依赖、任务队列或远端运行服务。

## 6. 下一项

继续 P0-05b，按[17 的 A01～A15](17-agent-tools-testing-plan.md)实现现有模型接口、T01～T05 handler、调用前预算预留、有界角色协作和安全摘要持久化。模型只提出受限建议；执行生成补丁仍须 P0-06 的隔离白名单与冻结验收。前端诊断页须随真实能力接通，不能提前标模型执行可用。

## 7. 最终整合追加记录

- 合入全部独立反例后的完整后端：**454 passed / 27 skipped（48.79 秒）**。保留项目 pytest 的 importlib 导入模式；取消该配置会让不同角色的同名测试文件发生收集冲突。
- 最终主目录 3010/8030 完整浏览器回归：**73 passed / 2 skipped（1.3 分钟）**；两项专用门禁已按第 3 节另行通过。旧文案断言问题关闭。
- 最终文案[独立复审 Pass](reviews/P1-01a-integration-docs-review.md)，修正阶段状态残留与 HTTP 408/413/415 错误说明。此追加不覆盖先前冻结快照。
