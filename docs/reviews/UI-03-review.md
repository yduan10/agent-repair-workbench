# UI-03 独立代码与界面评审

- 时间：2026-10-13。
- 范围：能力目录、侧栏与模块入口、首页状态、CLI 使用说明、验收锚点及相关测试/文档。
- 评审者：docs_review，独立于本次 UI 实现者；只在 `agent-sandboxes/p0-03-fixture` 保存评审副本和产物，未修改产品实现。
- 方法：auditing-enterprise-code-quality 的证据、门禁、十二维度原则；源码、真实 Chrome 交互、axe 和截图相互核对。
- 严苛度/场景：Mission-Critical / General SaaS；仅限可信本地 UI 增量。

## 1. 代码质量评估卡

**Pass。没有未关闭的已确认 Defect P0/P1/P2/P3。** 侧栏与实际能力一致，未把 CLI 已完成改成网页执行已开放。

```text
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100（本次约定范围）
VERDICT: scoped UI Pass
NOT ASSESSED: 容器/模型/后端实现不在本批 UI 评审范围。
```

### 能力与边界核对

- `capabilities.ts`：调用检查“网页可用”；connections“CLI 可用”；tasks“待接通”；diagnosis/repairs/regression/memory“待开发”。开发快照有日期，不冒充实时任务或健康状态。
- 侧栏、模块 topbar、首页状态读取同一目录。初审建议首页后两条也读取目录，作者已修改；未遗留单独硬编码的“规划中”标签。
- 每个尚未接通业务操作的模块都有“已完成的基础 / 现在怎么用 / 下一步”，并能跳到对应开发验收节点。
- regression 明确 284 项 Python / 18 项真实容器验收属于工程基础；同时明确尚不能执行用户项目的基线与候选对比。没有用工程测试数字冒充已完成的产品回归功能。
- MCP/容器 CLI 使用说明仅展示真实存在的固定配置路径，注明审核过的合成示例、已有基础镜像和显式准备；不是任意命令/仓库入口。未点击执行 Docker，也没有新增自动执行 API。
- Sidebar 原有全部 Link 保留 onNavigate guard；新增进度链接位于没有持久证据草稿的模块页，不绕过 workbench 的离页保护。

### 独立实际验证

使用 3010 的新版 production 页面，本机 Chrome / Playwright，独立探针保存在 `artifacts/ui-03-review/probe.mjs`，结果在 `browser-probe.json`。

| 验证 | 实际结果 |
|---|---|
| 浅色 1440×960 × 6 模块 | 状态正确，axe wcag2a/wcag2aa 0 违规，无横向溢出 |
| 深色 390×960 × 6 模块 | 状态正确，axe 0 违规，无横向溢出 |
| 两种组合下 CLI 展开 | 长命令正确换行，无横向溢出 |
| 两种组合下验收记录链接 | 到 `/updates#P0-03`，对应 summary 可见 |
| 模块浏览、CLI 展开与验收跳转 | 非 GET/HEAD 写请求 0 |
| 编辑调用证据后侧栏导航 | dismiss 留在 workbench，accept 正常进入 connections |

亲自查看独立生成的 `connections-light-1440.png`、`connections-dark-390.png`，确认能力区层次、状态标签、手机纵向布局和展开命令可读。初版探针的 axe 使用方式需显式 browser context，调整探针后得到上述实际通过结果；这不是产品缺陷。

主 Agent 的全量 19 项浏览器门禁另行记录：已有 18 项通过，剩余一项因旧全局文本定位器匹配多个区域而失败，已改成定位“真实能力进度”region。独立阅读修订后确认保留原断言含义，没有靠删除断言绕过问题；最后全量/定点复跑结果以主集成记录为准，本报告不预先宣称未完成的命令通过。

## 2. 生产事故风险推演

none：无已确认 P0/P1。本批没有新增后端操作、运行任务或凭据流。

## 3. 详细审计明细

- Defect P0/P1/P2/P3：均无未关闭项。
- 初审一致性建议：首页后两条状态改读统一能力目录，已落实。
- 测试维护：appearance 的重复文案定位改为有名称的 region，已静态复核；未发现产品行为故障。

## 4. 十二维度覆盖

| 维度 | 当前范围结论 |
|---|---|
| 架构与边界 | 能力目录统一；CLI、网页及未开发业务边界明确。 |
| SOLID/设计 | ModuleProgress 复用进度呈现，无重复控制逻辑。 |
| 并发与资源安全 | 无新增后台资源，导航 guard 保留且独立验证。 |
| 容错与防御性 | 页面为静态能力快照，不把不可用功能标成功。 |
| 性能与效率 | 无新增轮询/遥测/模型请求；CSS 使用既有变量。 |
| 安全与合规 | 代码文本仅展示，无命令执行与证据持久化新增路径。 |
| 可观测与运维 | 开发能力与验收链接清楚，不冒充运行时监控。 |
| 类型与契约 | CapabilityKey 限制目录键，标签统一来源。 |
| 可测试性 | 新增 progress 用例，独立 12 组 axe/状态/溢出及导航探针。 |
| 工程一致性 | 复用主题、details 与焦点样式；无新视觉依赖。 |
| 数据与事务 | 原始证据处理路径未改；历史仅追加新 UI 迭代。 |
| 依赖治理 | 本增量无新增依赖；未重复后端供应链扫描。 |

## 5. 整改清单

none。UI-03 完成状态需在主门禁通过后更新，不能据本报告提前写出未执行测试的数字。

## 6. 长效治理建议

1. 每个里程碑交付同时更新 capabilities、台账和历史，并保留按 ID 的状态断言，防止侧栏重新漂移。
2. 保持“工程验收证据”和“面向用户的已开放功能”两项分别描述，避免测试数量掩盖产品能力缺口。

## 7. 审计声明

- 本报告仅审 UI-03；本人参与过的 Docker/fixture 实现不在本报告独立审计范围，未重新执行容器故障矩阵。
- 独立 axe 覆盖 12 组 changed-module 组合；全站 36 组与真实 API 回归来自主集成测试，不能混称全部由本 reviewer 亲跑。
- 无 Safari/Firefox、屏幕阅读器人工验证、生产部署或整产品安全认证。axe 通过不等于完整 WCAG 认证。
- 无风险豁免。后续行为变更须按增量复审；仅有证据支持的完成状态更新可追加记录。

## 8. 最终静态增量复核

最终从主目录刷新并核对：UI-03 milestone 及对应状态断言改“已完成”，原七条历史未覆盖；六个模块 eyebrow 改成“能力与进度”，其下合成示例和不可执行提示仍保留；AGENTS 增加统一能力目录及工程验收/用户运行区别的同步门禁。以上改动未新增执行逻辑或样式。完成状态的发布仍应以主 Agent 最终构建、类型检查与完整 19 项 E2E 结果为前提；本 reviewer 不声称亲跑该主集成套件。

## 9. 评审快照摘要

| 文件 | SHA-256 |
|---|---|
| `frontend/lib/capabilities.ts` | `1f056c476e65a121d6309da0682e17327b79743890ba2d401003834bf93a64ef` |
| `frontend/lib/modules.ts` | `43c9f9c933d93adb9470268158e2ab4f8f852c874694675b90d7fad1c0b7982e` |
| `frontend/lib/milestones.ts` | `dc4453e7cd9cc8416b2146b5b224bc4d653db7a5a2222d795405d25ea8084805` |
| `frontend/components/module-progress.tsx` | `70cda50b3c9e2fae051237e711bd1bd2ac3503e3775a8872a059529a63c0f468` |
| `frontend/components/sidebar.tsx` | `0348969a089d638d9741b9ba0b30c89018e1823e217da30e163b391b2deb2ace` |
| `frontend/components/module-preview.tsx` | `1280760b7c19c6dd52b121c919ed37684c7f1bb1ebae33f82c8562647367555b` |
| `frontend/app/page.tsx` | `56605dc8a9c8ab59a78f2022cfde519a296e50eb5455e8cdbb97eeb595094ba6` |
| `frontend/app/globals.css` | `6d7d100595b6b7f48349681399788356e45da7f025e5c2f1ad08dc9916d68d28` |
| `frontend/app/updates/page.tsx` | `13d1c40ff9630176d54831144610cebe14caaef22df50f0f5b30f76fc7fb3b59` |
| `frontend/tests/progress.spec.ts` | `306dda596bb0580bd2fa0d7c611d2aa32fc4a40cddabec6f41eecb0e4d003f83` |
| `frontend/tests/appearance.spec.ts` | `d18db01332366fd90fbf492ecce6b691c14aaba8b3c64778284363be4ac78e10` |
| `frontend/tests/product.spec.ts` | `cbd99e1e79b2f8fd8aa88628d704a80fce0014b6869988121265ec1f278cddab` |
| `AGENTS.md` | `b18d18451a47aeab6b290863b8871fc757c7d918588783ce48b78a1dff6c1ed8` |
| `docs/13-ui-progress.md` | `cb1fd6dd8ae60bac99d895e480197841b68bf7b1aa8f0a409ee3d7b087fd0d00` |
| `docs/03-roadmap.md` | `b4688f28a43ca50af239b229bb9fb5824daea3302d7aee2dafa862543028f6e8` |

文档摘要记录本次复核时的版本；最终构建/测试数字追加属于交付记录，应与主集成实际输出保持一致，不改变上列前端代码的评审结论。

## 2026-10-13 产品介绍入口增量

用户指出静态0.1无对应发布依据；仅删除产品介绍链接内版本span。独立reviewer `/root/docs_review` 比对已审副本确认仅此一行变化，首页href与草稿onNavigate guard保留。production build通过，3010重启后读取实际HTML确认无版本徽标；未扩大测试范围。新的sidebar SHA-256：`91c85804dc9408f26a5f0deb6f067dc99c0252ba85e4bfb04a5c1f2b5d3b3a4c`。
