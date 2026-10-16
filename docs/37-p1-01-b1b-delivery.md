# P1-01 B1b：执行接续与安全恢复

2026-10-15。Feature P1。状态：planned → ready → in_progress → in_review → done。父任务 P1-01 保持 in_progress。依据：[B1 详细契约](35-p1-01-b1-admission.md)、[B1a 交付](36-p1-01-b1a-delivery.md)。本文记录内部实现；网页开始、停止及审批入口由 B2–B4 接入。

## 1. 本批实现

| 组件 | 变化 | 边界 |
|---|---|---|
| `RepairController.run_created` | 接收已提交的任务、一次性 claim 和已持有的 task fence；校验案例、基线、模型配置、预算、宿主策略与运行材料 | 不创建第二个任务，不重新获取 task 锁，不重新发放 claim |
| 原有 CLI 与网页内部执行入口 | 共用 `_loop`、角色切换、T05/T06/T07、预算预留和结算 | 两个固定审核案例，单角色或三角色；本批不增加 Agent 角色 |
| 停止与时钟 | 调用前读取持久取消；等待期间每 100ms 检查停止；600 秒从落库接收时间计算 | 消费前已登记停止零调用，调用后停止保留实际或未知用量；墙钟倒退拒绝继续 |
| `RecoveryService.recover_held` 与 Store held 方法 | 恢复、资源核对和对账使用同一把 task fence；原 CLI 包装自行持锁 | 修复旧路径清理后再次获取锁的间隙，不重放模型或工具 |
| `WebRepairRecovery.release_checked` | 全部资源先核验，显式 apply 才回收和对账；最后复核完整证据并释放 active | GET/inspect 不释放，单次或多次 absent 都不构成创建终结证明 |
| 接收账本释放事务 | 核对 receipt、task、request、candidate、T05/T07 计划/报告及事件的摘要，最后短事务 CAS | task revision 不变但 receipt 或证据变化也拒绝释放 |

网页仍用现有修复结果页查看 CLI 生成的候选和回归。站内文档目录增加本批记录，更新记录说明恢复边界；不添加尚未接通的执行按钮，不把内部验收结果混入用户运行列表。

## 2. 执行与取消语义

接收成功之后，只有持有原始内存 claim 的 owner 能调用 `run_created`。原 claim 被消费后，即使任务还停留在 ready，也不能重新执行。所有模型和工具动作沿用原有 durable reserve/settle，不因为增加网页入口绕过预算或候选验证。

owner 和 task fence 覆盖完整运行、等待以及资源清理。连续上层取消通过原有 `_owned` 等待实际执行收尾；取消监听器退出另有屏蔽，避免已完成结算后丢失返回结果。停止请求与外部请求已经发出存在竞争，不能把迟到取消记为零调用或零费用。

截止时间取持久化 started_at 加 600 秒，与单调时钟剩余量取较小值。接收后排队 590 秒只剩最多 10 秒；超过 600 秒不发起模型。运行期间墙钟倒退时不能继续扩展预算；无法确认结算的状态保留待对账。

## 3. 释放规则与已知限制

释放顺序为 web owner → task fence → 读取审计 → 事务外资源检查/回收 → 账本对账 → 再检查 → 短事务完整证据 CAS。所有身份通过预检后才允许删除任一容器，删除使用精确 ID；名称、镜像、命令、只读快照挂载或标签不一致均拒绝。

| 证据状态 | 处理 |
|---|---|
| 完整可信报告确认容器已移除，当前身份不存在 | 可继续核对账本并释放 |
| 宿主报告明确在发送 create 前返回，例如预算/Oracle/SDK/镜像前置校验失败 | 可继续核对；其余 `not_created` 错误不自动视为安全 |
| 合法中断 report=None，完整计划和 reconciled 事件存在；本次恢复找到并核验精确身份、移除后确认不存在 | 可释放，原 outcome_unknown 和未知用量保持 |
| 只有 inspect absent、PID 消失、等待一段时间或旧 CLI apply 成功 | 创建可能迟到，继续占槽 |
| T07 只有部分报告 | 没有报告的其余 slot 不能推测为“还没执行”；缺终结依据时占槽 |
| T06 发布未确认、attach 清理未确认、报告损坏或证据版本变化 | 保留 active，拒绝释放 |
| 接收后从未消费，owner 已退出 | 显式恢复原子消费旧授权并记录 INTERRUPTED；不执行任务，可在无资源后释放 |

本批不新增强制解锁。恢复过程曾移除容器但在证据提交前自身退出时，下一次只有 absent 仍不够；本批没有跨恢复进程持久化 quiescence 证明。这种故障保守阻塞，不能承诺所有中断都能自动恢复。临时结果未知不会被改写为通过，模型未知预留不会清零。

## 4. 测试与独立评审

测试使用临时 SQLite、真实快照与文件锁、确定性时钟、脚本化模型及 Docker double。测试不消费现有模型网关、不迁移主库、不声称新增真实模型修复成功率。真实 Docker、模型和网页整体链路属于 B5。

| 契约 | 断言与用例 |
|---|---|
| B1-06/08 | 消费前取消/超时零调用；已发调用后取消保持已知用量或未知预留；接收延迟不重设期限；时钟倒退不发新调用 |
| B1-10 | 两案例 × 两模式完成 T05/T06/T07；旧 CLI 控制器回归；已消费/已完成 claim 不可重入 |
| B1-11 | 资源身份失配、回收失败、unknown cleanup、attach 清理未知、T06 未决、finished 缺报告、T07 部分报告均拒绝释放 |
| B1-12 | 完整报告安全释放；未消费授权仅退休不执行；合法缺报告对账并取得正向资源证明后释放，历史未知状态和预留不变 |
| B1-14 | 第一次 absent 保留活动槽，迟到精确容器出现后核验、回收才释放；不启动第二次修复 |
| 竞态 | 连续上层取消期间两把锁不能接管；检查期间及最终 CAS 前的 receipt 改动被拒绝；原 CLI held 恢复 CAS 回归 |

执行命令：

```bash
uv run --frozen pytest tests/test_web_repair_execution.py tests/test_repair_recovery.py tests/agents/test_repair_controller.py tests/agents/test_repair_controller_review.py
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv lock --check
cd frontend
npm run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/reviewer-document-reader.spec.ts --grep 'all registered docs'
```

最终代码验收：

| 验证 | 实际结果 | 本地产物 |
|---|---|---|
| 全量 Python | **1484 passed / 66 skipped**，181.11 秒；跳过项不计通过 | `artifacts/b1b-python-full.log` |
| 新旧执行/恢复定向回归 | **84 passed**，29.92 秒；已包含于全量，不重复累计 | `artifacts/b1b-targeted5.log` |
| 独立复审 | **Pass**；新增 3 项独立 CI 反例，加连续取消 1 项均通过 | [独立代码评审](reviews/P1-01-B1b-code-review.md) |
| 静态检查 | Ruff、格式 385 文件、mypy 130 源文件、uv 锁检查通过 | 执行上方命令 |
| 前端生产构建 | 通过 | `artifacts/b1b-frontend-build.log` |
| 站内文档链接 | Chrome：1 passed，127 页、120 个交叉链接、零断链 | `artifacts/b1b-doc-links-chrome.log` |

独立评审采用企业代码质量审计 skill，由未参与实现的 reviewer 执行反例测试。初审 Defect P1：取消监听器收尾再次被取消导致结果丢失，已修复并独立复测；无未修 P0/P1。报告列出本批 8 个生产文件的精确 SHA。全部运行产物只存本地，不进入源码仓库。

早期失败记录保留：测试夹具误用案例加载器、Usage 字段和 Mutation 子类比较，旧恢复测试注入点需要跟随 held 入口调整；连续上层取消暴露监听器收尾二次取消，生产实现已加 shield，修复后的定向测试通过。上述失败未被删去或计作通过。前端首次测试因未安装 Playwright 默认浏览器未启动，改用本机 Chrome，不下载额外浏览器；失败日志为 `artifacts/b1b-doc-links.log`。

## 5. 基线、部署与下一批

B1a 已按用户授权提交并推送至 main，提交 `40d3e34`，GitHub CI 已成功。B1b 交付时尚未提交；后续已按用户授权提交并推送 `a68dde0`，GitHub CI run `38732440480` 成功。

源代码使用 0008；本机既有后端仍运行旧代码与 0007 主库。本批保持主库及后端不变，仅更新前端站内文档。启用新后端前仍需按 [36](36-p1-01-b1a-delivery.md) 停写、备份、显式迁移与逐表核验。

B1b 验收通过后进入 **B2：固定案例目录、开始/取消 API、owner 生命周期和恢复检查**，并验证复现/分析/修复三个槽的组合边界。随后 B3 将实际执行接入现有修复页；B4 人工审阅决定和补丁下载；B5 真实链路验收。B1b 内部完成不代表网页已经可发起修复。
