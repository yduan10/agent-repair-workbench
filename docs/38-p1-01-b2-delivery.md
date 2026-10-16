# P1-01 B2：修复运行 API 与任务生命周期

2026-10-15。Feature P1。状态：planned → ready → in_progress → in_review → done。父任务 P1-01 保持 in_progress。依据：[34 网页修复设计](34-p1-01-web-repair.md)、[35 接收与执行契约](35-p1-01-b1-admission.md)、[37 B1b 执行与恢复](37-p1-01-b1b-delivery.md)。全量回归、独立复审与前端文档验收均通过。

## 1. 已实现范围

| 入口 | 输入与行为 | 结果 |
|---|---|---|
| `GET /api/repair-runs/catalog` | 固定案例、模式、预算、本地材料与配置状态、当前活动槽 | 只观察，不连接 Docker、不执行模型、不迁移或清槽 |
| `POST /api/repair-runs` | 严格 `{request_id, case_id, mode}`；两个案例 × 单角色/三角色 | 同事务保存任务、事件和接收记录后返回 202；同参历史返回 200，不重新执行 |
| `GET /api/repair-runs/{request_id}` | 查询原接收记录及任务摘要 | 不发 claim，不执行恢复 |
| `POST /api/repair-runs/{request_id}/cancel` | 仅接受空 JSON 对象 `{}` | 持久登记停止；活动任务 202，已结束 200；不将停止登记当作停止完成 |

仅支持 `output_mismatch`、`counter_offset`；模式为 `single_role`、`three_role`。不得传入路径、源码、Shell、模型、密钥或验收规则。既有 `/api/repairs` 继续提供候选、差异与回归读取。

`web_repairs/service.py` 管理独立于请求连接的 owner；实际模型、T05/T06/T07 与角色循环复用已有 RepairController。没有增加产品 Agent 或重复实现修复循环。

## 2. 接收、取消与停止

1. 同参历史查询先于模型配置、adapter 和镜像检查，依赖不可用也能查看已有任务。
2. 新请求持有 repair web owner，再获取原 task fence；持久事务提交后才响应。claim 永不进入 HTTP 响应、日志或事件。
3. 客户端断开只停止等待；已注册的服务任务继续持锁并完成执行/收尾。提交回执丢失时，使用原 ID 查询；不自动启动第二次执行。
4. 取消写入数据库，由共享 controller 每 100ms 观察，沿用原预算结算。远端是否停止、是否产生费用未知时仍保留未知预留。
5. lifespan 关闭时先拒绝新接收，再登记停止并等待 owner 收尾。重复取消 shutdown 等待者也不提前释放锁。
6. SIGSTOP 不释放文件锁；别的 worker 不能因超时接管。owner 退出后有活动记录时，仅新的明确提交可进入原恢复检查，不能重放旧任务。

只读及接收等待分别最多 2 项；SQLite 线程仍在执行时，即使 HTTP 等待者取消，读取容量也等线程完成后再归还。JSON 限制 4 KiB / 5 秒，沿用本机 Host/Origin；响应 `no-store`，错误为固定代码，不回传原始异常。

目录中的本地镜像就绪只说明材料通过校验；新提交还会在 8 秒限制内 inspect 已准备镜像并核对 ID。接口不拉取或构建镜像。前置失败不消费模型预算。

## 3. 组合资源边界修复

本轮同时审查了旧复现/分析槽，独立评审发现并修复两类问题：

- **对账观察不构成释放凭据**：删除 `reconciled + absent/stopped` 直接释放分支。未决 create 可能迟到，只有可信完成报告和正向终结/清理证据才可释放。
- **保留 attach 清理未知**：runner 的原执行错误、oracle 后置校验与原生取消不能覆盖 `attach_cleanup_unconfirmed`。否则容器虽然删除，仍有未确认进程，槽却可能提前放行。

同一状态目录下：复现、分析、修复各 1 个活动槽；本地仍等待的模型请求最多 2 个；潜在受控容器最多 3 个。组合实验以可计数的模型/执行替身验证三槽同时占用，以及 unknown 后全部拒绝新任务。真实 Docker 配额与完整网页链路仍属于 B5，本轮不声称重新测得真实容器峰值。手工 CLI、其他目录及断连后远端模型计算不计入该范围。

旧槽缺乏正向终结证据时可能持续阻塞。本轮没有强制解锁；不得编辑账本、改未知为成功或删除记录绕过保护。runner/oracle 源码变化会更新安全闭包摘要；旧报告原样保留，不重签为新版本，页面按既有版本校验撤回失配的通过显示。

## 4. 测试矩阵与证据

| 组别 | 实验 | 必须保持的结果 |
|---|---|---|
| API 契约 | 四种案例/模式、严格 DTO、Host/Origin、体积/类型、未知 ID、缺库 | 合法接收；非法输入无执行；缺库不自动建表 |
| 幂等 | 历史重提交、当前配置失效、commit 后回执丢失 | 返回同一任务，不重发模型或新 claim |
| HTTP / 多进程 | 真实 TCP、两个 Uvicorn worker、并发提交、发完请求即断连 | 接收与 HTTP 寿命分离；一次实际模型边界调用 |
| 跨 worker 停止 | 另一 worker 登记停止、owner SIGSTOP/CONT | 停止可见；暂停期间锁与槽仍占用 |
| 服务关闭 | Uvicorn SIGTERM、preflight 期间 shutdown、重复取消等待者 | 停止接收，等待收尾；无新增执行 |
| 容量 | 读取协程取消但 SQLite 线程未退出 | 不提前归还读取容量 |
| 三槽组合 | 同目录三服务并行、2 个模型等待、3 个潜在执行、未知后再提交 | 不穿越各自活动槽，无额外执行 |
| 资源反例 | absent/stopped 对账、attach 与其他错误叠加、原生取消 | 未知保持未知，不提前释放 |

所有模型和 Docker 边界使用确定性替身；SQLite、文件锁、TCP、Uvicorn worker 和信号是真实运行。数据仅在临时目录，未访问用户模型网关或迁移用户主库。测试通过数不能解释为模型诊断/修复成功率。

```bash
uv run --frozen pytest
uv run --frozen pytest tests/test_web_repair_api.py tests/test_web_repair_http_workers.py tests/test_b2_combined_slots.py
uv run --frozen pytest tests/test_b2_api_review.py tests/test_b2_resource_review.py
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv lock --check
cd frontend
npm run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/reviewer-document-reader.spec.ts --grep 'all registered docs'
```

| 验证 | 结果与产物 |
|---|---|
| 全量 Python | **1524 passed / 66 skipped**，180.53 秒；`artifacts/b2-python-full-final.log` |
| API 与真实 HTTP 双 worker | 20 passed；`artifacts/b2-http-tests.log` |
| 三槽组合 | 1 passed；`artifacts/b2-combined.log` |
| 独立 API 反例 | 8 passed；[API/service 评审](reviews/P1-01-B2-api-review.md) |
| 独立资源反例及相关回归 | 122 passed / 3 skipped，其中独立反例 11 项；[资源评审](reviews/P1-01-B2-resource-review.md) |
| 静态检查 | Ruff 通过，格式 397 文件，mypy 133 源文件，uv lock 78 包检查通过 |
| 前端生产构建 | 通过；`artifacts/b2-frontend-build.log` |
| 站内文档链接 | Chrome：1 passed，130 页、124 个交叉链接、零断链；`artifacts/b2-doc-links-chrome-final.log` |
| 旧槽断言增量复审 | 55 passed；包含两份旧槽测试、独立资源反例与三槽组合，详见资源评审追加记录 |

各分组包含于全量或相互重叠，不能累计为额外通过数。首次全量为 1522 passed / 2 failed / 66 skipped：两个旧测试仍期待 absent 对账后释放，已按冻结规格改为保留槽，并由独立评审增量核对；正常正向证据释放测试保留。早期 API 夹具将 None 当作无 JSON 请求，触发 415，修正为显式 JSON null 后通过。失败产物保留，不计通过。文档浏览器检查第一次从项目根目录启动，测试按 frontend 相对目录读取文档而失败；按上方命令进入 frontend 后重跑通过。全量有 1 项 fork 测试触发 Python 多线程 fork 弃用警告，不计作失败或跳过。

## 5. 独立评审

按企业代码质量审计 skill 拆为 API/service 与资源安全两个子批，分别由独立 reviewer 审查并写反例。生产文件 SHA-256 见对应报告；API 范围通过，资源范围两类 Defect P1 已修复并复审通过。没有未关闭的 Defect P0/P1。全量回归、前端构建与文档检查通过，9 个生产文件摘要与独立评审逐一匹配，本批关闭。

## 6. 提交、部署与下一步

- B1b 已按用户授权提交并推送：`a68dde0c8cfd2e82d8ef67dbcd56bd1d752f2ed0`，GitHub CI run `38732440480` 成功。本批 B2 尚未提交或推送。
- 源码要求 schema 0008。本机 0007 主库尚未迁移；收尾核查时 8030 无监听，主后端尚未启动新版本，本次 API 集成在隔离临时库验证。现有 8030 服务不能据此视为已经提供新 API。
- B3 接通网页前，按 [36 的迁移步骤](36-p1-01-b1a-delivery.md) 停写、备份、显式迁移、逐表保真核对并重启；旧程序不应直接使用新库。保留迁移前备份，禁止带数据降级。
- 前端本轮增加站内 API 实现/限制记录和更新入口。修复页保持“网页只读”；B3 才加入案例/模式选择、开始/停止、pending 持久化、断线查询与刷新恢复。
- B4 实现人工审阅决定和补丁下载；B5 以现有真实模型、Docker 与浏览器完成端到端验收。候选接受不等于自动写回项目。
