# UI-01 / P0-02 设计增量评审

2026-10-13；独立只读 reviewer `/root/docs_review`；实现与修订 `/root`。

## 范围与结论

检查 01/02/03/04 与 07 产品界面、08 MCP 接入规格、README、Playwright/CI 配置的一致性和可验收性。最终复审 **Pass，可冻结本轮规格，无剩余 Defect P0/P1/P2**。

本评审未重跑代码测试、安装 MCP SDK 或复现公开问题。UI/API 代码与测试证据见 UI-01-code-review.md；本结论不替代 P0-02 实现后的代码评审。

## 发现与整改（均为 Defect P2）

| ID | 发现 | 修复与复审 |
|---|---|---|
| DOC-UI-01 | 旧规格仍将UI整体后置至M3 | 01/02/03/04/07统一完整界面先行、后台逐项解锁 |
| DOC-M1-01 | M1默认容器约束与P0-02本机fixture边界不一致 | 明确仅审核fixture/固定历史案例的受控实验；硬隔离从P0-03起 |
| DOC-M1-02 | 接入页容易被理解为P0-02直接开放用户命令 | 文案改为受控示例先行、自定义接入待执行隔离 |
| DOC-M1-03 | outcome、CLI码、预检及总时间缺少统一oracle | 新增状态表、preflight_findings、缺失Report、退出码；合法输入不得被result_missing拦；20秒含所有检查，清理另3秒 |
| DOC-M1-04 | 旧“超时均unknown”句与分阶段状态表冲突 | 仅call已发出且无可靠终态时outcome_unknown |
| DOC-CI-01 | Playwright启动API未冻结依赖 | 增加uv run --frozen，命令在frontend目录实际解析成功 |

复审确认 SDK 钩子移交验证责任、normalized 与 wire 保真的区别、真实ID与本地关联ID的区别均明确。公开 issue 的受影响候选SHA不写成修复SHA，未把issue关闭状态写成复现成功。

## 冻结后的下一步

UI-01按代码与浏览器证据关闭；P0-02可按08进入SDK兼容实验、证据适配和真实stdio开发。公开案例、SDK项目lock和实际MCP调用仍待执行。
