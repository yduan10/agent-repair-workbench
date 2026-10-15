# 企业代码质量审计报告

- **审计对象**：P1-01b 前端网页执行控制台批次；诊断分析、MCP 复现入口与接口目录接缝。
- **审计版本**：工作树。文件摘要见文末及 `artifacts/console-review-sha256.json`。
- **技术栈**：Next.js、React、TypeScript、Zod、Playwright、axe-core。
- **业务场景**：General SaaS；实际使用边界是本机可信单用户工具。
- **审查严苛度**：Mission-Critical。
- **审计时间**：2026-10-14（Asia/Shanghai）。
- **独立评审者**：p006_contracts；未参与该批生产实现，仅编写独立反例和本报告。使用 auditing-enterprise-code-quality、frontend-design、web-design-guidelines。

## 1. 代码质量评估卡

- **综合质量得分**：**100 / 100**，按修复后当前范围的未解决发现计分，不代表产品成熟度。
- **上线评估结论**：**Pass：允许前端控制台批次整合**。不替代 P1-01b 真实模型、真实执行器和临时数据库的端到端验收。
- **审计范围**：8 个前端文件的约 1000 行批次；另核对前后端接口目录版本增量。证据阅读组件由另一评审独立审查，本报告只检查其控制台接缝。
- **未评估项**：范围内 none；HTTP/账本实现、真实模型和容器执行、旧复现请求存储策略在本批之外。复现面板本次仅审 compact 展示增量及调用接缝。全项目发布必须补齐各批门禁。

**修复后缺陷汇总**

| P0 阻断 | P1 严重 | P2 主要 | P3 次要 |
| :---: | :---: | :---: | :---: |
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: none remaining -> 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100 (this batch only)
VERDICT: Pass after cancellation fix and independent retest
NOT ASSESSED: real model/container/API lifecycle and other implementation batches
```

## 2. 生产事故风险推演

### 取消请求失败与切换记录交错（已修复）

- **触发条件**：用户在任务 A 请求停止，等待期间查看 B；A 的取消请求返回 503，再返回仍运行的 A。
- **失效机制**：旧实现仅在 `currentTask === A` 时清除 `stoppingTask`，错过失败后的状态恢复。停止按钮一直呈现“正在停止…”，没有可点击重试入口。
- **用户可见症状**：服务端任务继续执行，网页却无法再次取消。影响单浏览器会话；刷新能绕过，不构成数据破坏。
- **可检测性**：旧测试未覆盖这一异步交错；独立反例在修复前确实失败，修复后通过。

另外核对了丢失 POST 响应后的同 ID 重查：重查 429 不清本地 pending；只读 catalog 的短暂 429 只重试 GET，最多 5 次重试，始终不自动重发 POST。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

#### C-1. 取消状态未完全按任务关联恢复 — 已修复

- **位置**：`frontend/components/analysis-console.tsx:19`、`:100`，取消状态和 `stop()`。
- **维度**：并发、异步与资源安全；容错。
- **置信度**：[confirmed]。
- **问题分析**：全局布尔 stopping 会串用不同记录；首轮任务 ID 修复后，迟到失败仍因当前选择不同而不清原任务停止状态，破坏停止失败可重试的控制契约。
- **负责人**：root。
- **最小修复**：停止状态绑定 task_id；每任务同步 stopGuard 阻止同帧重复取消；失败总是有条件清理该任务的 stoppingTask，只有提示文案按当前选择更新。终态清理不依赖本地 pending。

```diff
- if (alive.current && currentTask.current === taskId) {
-   setStoppingTask(null);
-   setMessage("停止请求尚未确认，请刷新状态或再次请求停止。");
- }
+ if (alive.current) {
+   setStoppingTask(previous => previous === taskId ? null : previous);
+   if (currentTask.current === taskId)
+     setMessage("停止请求尚未确认，请刷新状态或再次请求停止。");
+ }
```

- **验证**：独立测试“离开期间取消失败，返回原任务仍可重试停止”修复前失败（无法找到可用“停止执行”按钮）；修复后与另 7 个独立反例全部通过。

### P2 — 主要缺陷

none remaining。

### P3 — 次要缺陷

none。

### 验证证据

测试采用 Chrome、3012 前端开发服务。执行/取消/分析读取全部使用 Playwright route mock；接口目录接缝只读现有 `/api/agent-contracts` 的结构，再模拟版本 3/2。没有向主数据库提交执行、没有调用真实模型。

```sh
cd frontend
PLAYWRIGHT_CHANNEL=chrome PW_PORT=3012 npx playwright test tests/console-review.spec.ts tests/console-evidence.spec.ts --reporter=line
```

```text
17 passed (14.3s)
```

其中 `console-review.spec.ts` 是本次新增的 8 个独立测试：

1. 取消外部已有任务后，新占用任务仍可停止。
2. 同一帧连续点击开始，只产生一次 POST。
3. 丢失提交响应后离页再进入，保留请求 ID，不自动 POST。
4. 切换任务后旧取消成功响应不污染当前控制台。
5. 配置目标后，键盘 Tab/Enter 启动、Space 切换跟随、反向 Tab 聚焦事件区域；390px、深色、减少动效。
6. 离开期间取消失败，返回原任务可以再次停止。
7. catalog 两次 429 后恢复，始终没有自动提交。
8. 展开“角色与工具接口”后，接受版本 3/网页可用标记，拒绝旧版本 2。

原 9 项测试包含浅色/深色 × 1440/390px 的无溢出与 axe 检查，以及未知提交重查 429、存储拒绝、刷新无重复执行。已查看浅色桌面和深色手机截图；操作与结果分层，事件区高度受限、内部滚动，长 ID 默认不挤占控制区。

```sh
npm run typecheck
```

```text
> agent-workbench-ui@0.1.0 typecheck
> tsc --noEmit
```

退出码 0。

**测试过程中的非产品失败**：系统没有默认 Playwright Chromium，使用已安装 Chrome 后正常；键盘测试原先用 Home/ArrowUp 直接更改 Mac 原生下拉选项不可靠，改为 selectOption 设置测试前提，再验证实际键盘启动与焦点。旧 `agent-contracts.spec.ts` 尚按未折叠布局直接寻找接口区域，且当时 8030 尚未重启提供版本 3；该旧套件未通过，已交实现者更新入口并在新 API 上重跑，不能把本报告写成“全部前端测试通过”。本报告的版本 3 测试是明确的 mock 接缝测试。

## 4. 维度覆盖声明

| # | 维度 | 未解决发现 | 结论 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 页面只提交固定案例/意图，不接收任意命令；Next 只转发白名单路径 |
| 2 | SOLID 与现代设计 | 0 | 终端展示组件、请求 codec、页面状态职责分离 |
| 3 | 并发与资源安全 | 0 | C-1 已修；同步提交 guard、取消 task guard、卸载 abort、轮询清理 |
| 4 | 容错 | 0 | pending 先保存；不确定响应保留 ID；catalog GET 有限重试 |
| 5 | 性能 | 0 | 事件受服务契约上限限制、固定高度滚动；无无限 POST 或计时器叠加 |
| 6 | 安全与合规 | 0 | 固定请求 schema，不显示原始错误/密钥/模型原始文本；来源文本由 React 转义 |
| 7 | 可观测性 | 0 | 状态、取消请求与实际终态分开，显示真实结构化事件而非模拟日志 |
| 8 | 类型与契约 | 0 | Zod strict、UUID/摘要、返回 task_id/intent 关联校验，目录版本前后端同步 |
| 9 | 可测试性 | 0 | 新增 8 个反例；旧目录测试入口需在总验收同步 |
| 10 | 工程规范 | 0 | 主题变量、语义标签、可见焦点、技术信息折叠；未引入新视觉系统 |
| 11 | 数据完整性 | 0 | 本地 pending 不作为执行完成证据；同 ID 重查不重新生成任务 |
| 12 | 依赖治理 | 0 | 本批无新增依赖；未重新进行全项目供应链扫描 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| C-1 | Defect P1 | root | 本批整合前 | 已修复，独立复审通过 |
| 验收后续 | 测试接缝 | root | P1-01b 完成前 | 更新旧目录测试折叠入口，新 API 版本上线后重跑；完成真实端到端 |

## 6. 架构防腐与长效治理建议

1. 保留独立取消交错反例为回归门禁；后续异步操作均以任务 ID 关联 UI 状态，成本是维护本次已有测试。
2. 保持 catalog GET 与执行 POST 的重试策略分离；不要抽成统一“自动重试 fetch”，以免重新引入未知提交重复执行。
3. 控制台布局改为折叠/抽屉时同步测试的用户入口；能力版本和健康检查仍分别建模，避免“有能力”被误读为“当前可运行”。

## 7. 审计声明

- 本报告只覆盖上述批次；真实模型/容器、临时库端到端和其他模块评审是独立门禁。
- 豁免：none。未保留 suspected 缺陷驱动结论。
- 当前能力限定为审核过的案例与 P0-05 分析建议，不声明支持任意 MCP 服务或网页应用 P0-06 补丁。
- 评审版本摘要如下；后续修改需按影响范围复审。

```json
{
  "frontend/components/analysis-console.tsx": "6a479c64308390161e822c360bfdd2bb65f3f899b22610872fe2d0889f9f23cd",
  "frontend/lib/analysis-runs.ts": "03bf8c662c7f8f4111b6176f00636cd3fd72bcd7cb259269fa90b46a071044b7",
  "frontend/components/execution-terminal.tsx": "38db51aac06a8e1d97a5241e46453ecf3933a2198078fa6172c2f342ddf6e911",
  "frontend/components/connections-console.tsx": "d35816debd6d38307a896cc1b3d6a9d198b9a72cdfbd7659362fc9d73d0750d6",
  "frontend/components/reproduction-panel.tsx": "816a85b32bdbfdf21fd7594cbc452b47b30252ecbfdf6cdb3443fe58fa10eea0",
  "frontend/components/analysis-history.tsx": "96807278b15280309ced1cc843b8e3ea6fd1fd613b7bba75d57f0634681e3eb7",
  "frontend/next.config.ts": "7d6c86ae91c96f1933e3ac0a42101b3b7f5ab8dbc2feb5b0379ecdd2e89f8933",
  "frontend/app/globals.css": "9d27fd5e5768030c7e4bce6e05292cabd131285e7f1fcebef4e20beb5323208a",
  "frontend/lib/agent-contracts.ts": "ab261c828d23bff254c632e568f6c7d331b98ef87eca7cff75ec928e91ef56bf",
  "src/agent_workbench/orchestration/catalog.py": "20a591af2e791cfbc128fdb4d47a4929fc78124854e770f4f02e8cc4963673ee",
  "frontend/tests/console-review.spec.ts": "6ddc3115a8b51ec5e4f3f0a39d0984a120106845e9a8498ab6650bda71aadb05"
}
```
