# UI-08 外壳、复现与公开页面缺陷修复复审

- **审计对象**：原 `UI-08-shell-review.md`、`UI-08-runs-review.md`、`UI-08-public-review.md` 已列缺陷的修复及直接回归。
- **审计版本**：`HEAD 802bf70` 上的当前工作树；文件指纹见文末。
- **技术栈**：Next.js 16.4、React、TypeScript、Playwright；CLI 命令边界使用 Python argparse。
- **业务场景**：General SaaS（可信本机单用户产品）。
- **审查严苛度**：Mission-Critical；仅对声明的修复范围应用门禁。
- **审计时间**：2026-10-15（Asia/Shanghai）。
- **独立性**：评审者没有实现或修改生产代码；新增 `frontend/tests/ui08-shell-followup-independent.spec.ts`，执行定向回归。未构建、启停服务、提交或推送代码。

## 1. 代码质量评估卡

- **结论**：Pass，限本报告三批缺陷修复。原有 9 项 Defect P2 已修复并复验；没有未修 Defect P0/P1/P2。
- **残余缺陷**：12 项原评审 Defect P3 继续跟踪，不把它们写成已修复。
- **范围分批**：A 为 shell D1–D5 及相关 D6–D15；B 为 runs D1–D2 及相关 D3–D10/S1；C 为 public D1–D2 及相关 D3–D8。分别核对修复点及直接调用方，不重审三份原报告覆盖的整个模块。新增代码体量没有跨过单批约 2000 行的门禁。
- **未评估项**：范围内 none；完整生产发布、全部页面、模型效果、后端并发/沙箱安全与跨浏览器矩阵不属于本报告。依赖于其他 UI-08 评审和整体交付门禁。

| P0 | P1 | P2 | P3 |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 12 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 12 confirmed P3 × 1 = 12
RAW SCORE: 88
CAP APPLIED: none
FINAL SCORE: 88 / 100 (需关注，残余均为跟踪润色项)
VERDICT: Pass — 本轮原 P2 修复通过，无未修 P0/P1/P2
NOT ASSESSED: none within declared fix scope
```

### 复验结果

| 批次/原发现 | 本轮核对 | 证据 |
|---|---|---|
| shell D1 | 分析目录首次失败显示无法读取；连续两次失败撤回上次就绪值；成功刷新恢复 | 作者缺陷测试 + 独立失败→恢复探针 |
| shell D2 | 弹层 `left/right:0` 限制在侧栏；1440/390 宽度不裁切、侧栏不横向溢出 | 作者缺陷测试两尺寸 |
| shell D3 | 关闭抽屉 inert；打开聚焦首导航；正文 inert；Esc 恢复按钮焦点 | 作者缺陷测试 |
| shell D4 | 失败数据源明确列出；部分失败不显示「还没有记录」 | 作者缺陷测试 |
| shell D5 | 路由变化取消确认；运行停止路径另有 mounted 检查，离页不发送迟到停止 | 作者缺陷测试 + 代码路径核对 |
| runs D1 | 返回列表改按钮滚动并聚焦标题；选择写 URL 时清空 hash；手机后退选中一致 | 作者缺陷测试 + runs 回归 |
| runs D2 | 非四种网页场景使用中性结果描述，不断言符合或不符预期；关联不符与清理未知保护保留 | 作者缺陷测试 + reproduction-result 独立回归 |
| public D1 | 落地页复用 REPAIR_COMMAND；不再展示当前 CLI 不支持的 --case | 真实 argparse 命令解析测试 |
| public D2 | README 页面表、docs/27 主要页名/能力、修复命令已同步当前路由和单案例边界 | 文档源码比对 + 文档浏览器回归 |

### 实际运行

1. `PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/ui08-review-fixes.spec.ts tests/runs.spec.ts tests/reproductions.spec.ts tests/reproduction-result-independent.spec.ts tests/progress.spec.ts tests/document-reader.spec.ts tests/reviewer-document-reader.spec.ts --trace off`
   - 第一轮：`67 passed (1.4m), 2 failed`。两失败均为旧测试断言：自动选中不许出现 `?run=`、返回列表仍要求 link，和已经修复的行为相冲突。不是隐藏失败后宣布全绿。
   - 实现者更新这两个断言后独立重跑 `tests/runs.spec.ts`，`17 passed (11.8s)`，包含两项原失败和其余全部 runs 回归。第一轮69个不同用例现均有通过记录；没有把重跑次数累加为新增测试。
2. `PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/ui08-shell-followup-independent.spec.ts --trace off`
   - `4 passed (3.2s)`。验证连续失败撤回旧环境、成功恢复、busy 精确链接/Esc 焦点、草稿导航 guard、时长进位。
3. `uv run --frozen pytest tests/test_frontend_cli_commands.py -q`
   - `.... [100%]`，4 项通过。

浏览器写操作用例均拦截相应 API，未向真实主数据库发送开始/停止请求。文档与外壳只读取真实服务。所有测试使用已运行的 3010 dev 前端与 8030 API，不可冒称 production build 验收。文档遍历输出 `pages=111, localLinks=104, broken=[]`。文档和复现回归包括浅/深色与 390/1440 布局及 axe 检查。

## 2. 生产事故风险推演

none：本范围没有未修 P0/P1。已覆盖的典型故障为目录读取失败、部分记录读取失败、离页时确认未完成，以及手机历史状态错位。修复没有增加任意命令、模型调用或写入权限。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

none。原 9 项闭合见第 1 节。旧断言同步是本轮实际发现并修正的回归门禁缺口。

### P3 — 次要缺陷（保留原编号，不重复报成新问题）

以下均 `[confirmed]`，按代码核对保留；原报告的动态证据仍可参考，本轮不宣称重新复现全部 P3。

| 跟踪 ID | 位置 | 剩余问题与后续修法 |
|---|---|---|
| UI08-S-D9 | `frontend/app/(app)/error.tsx:4` | 仍用 reset；缺 global-error。按本地 Next 文档评估 retry，并补全外壳失败页。 |
| UI08-S-D10 | `frontend/components/environment/commands.ts:5,25`、`frontend/lib/environment.ts:41` | 启动命令/地址写死 8030，与可配置端口不一致。统一注入配置或避免固定地址文案。 |
| UI08-S-D12 | `frontend/app/layout.tsx:21`、`frontend/components/ui/theme-switch.tsx:9` | theme-color 只随系统媒体条件，不随手动主题；同步 meta。 |
| UI08-S-D13 | `frontend/lib/capabilities.ts:20` | connections 标网页可用、同类只读页标网页只读；统一状态口径或写明设置页规则。 |
| UI08-S-D15 | `frontend/components/ui/path-trail.tsx:9` | generic span 设 aria-label；明确 role 或提供完整读屏文本。 |
| UI08-R-D6 | `frontend/components/reproduction-panel.tsx:57-99,190` | 待确认请求持续 404 时不能显式放弃；查询结束仍有「正在查询」。应有说明风险的人工放弃入口，绝不自动重发。 |
| UI08-R-D10 | `frontend/tests/reproductions.spec.ts`、`frontend/tests/ui08-review-fixes.spec.ts` | D1/D2 覆盖已补；筛选后退、pending404 放弃以及场景 reduced-motion 的专门断言仍需补齐。 |
| UI08-P-D3 | `frontend/app/page.tsx:64` | 文案仍暗示四复现场景直接交给模型；实际分析接固定案例。分别描述两个入口。 |
| UI08-P-D5 | `frontend/app/page.tsx:25,32`、`frontend/lib/milestones.ts:148` | `--user 65532` 与实际 uid:gid 写法、超时名称、退出码2解释需统一。 |
| UI08-P-D6 | `frontend/app/docs/[...slug]/page.tsx:16-19,43` | 元数据继承通用描述，部分导航名与文档标题不一致。使用登记 title/summary 生成元数据。 |
| UI08-P-D7 | `frontend/app/docs/[...slug]/page.tsx:38,71` | sidebar/toc complementary 无命名、重复 region label；添加准确的 landmark 名称。 |
| UI08-P-D8 | `frontend/tests/guidance.spec.ts:25-34` | 空态用例依赖真实单并发检查器，与其他测试并行可能429；改mock或独立隔离状态。 |

原 shell D6/D7/D8/D11/D14 已修复：busy 链接、Esc 焦点、草稿 guard、时长进位、h1 与模型术语。原 runs D3/D4/D5/D7/D8/D9 及疑似 S1 已有相应修复；对未逐项新建动态探针的 P3，只记代码核对，不虚增测试数。public D4 单案例限制已补入落地页。

另检查到 `docs/27-local-development-guide.md:186` 仍把 MCP 运行入口写成 connections，实现者已修正为 tasks，本轮再次读取确认。该小项已闭合，不计入12项残余P3。

## 4. 维度覆盖声明

| # | 维度 | 结果 |
|---|---|---|
| 1 | 架构与边界 | 原边界保留；目录只读、启动/停止权限未扩大 |
| 2 | SOLID 与现代设计 | 共用修复命令，消除文案重复来源 |
| 3 | 并发与资源 | 两次失败撤回旧值、离页 mounted/abort、历史导航相关核对 |
| 4 | 容错 | 部分读取失败不作空记录判断；未知保留未知 |
| 5 | 性能 | 弹层不引入额外轮询；本次未改吞吐策略 |
| 6 | 安全与合规 | 未扩展写权限；测试不泄露凭据或原始异常 |
| 7 | 可观测性 | P3 端口/用户说明继续跟踪，其余失败可见 |
| 8 | 类型与契约 | 原 strict schemas 与报告关联核验保留；CLI 用真实 parser |
| 9 | 可测试性 | 独立4例；旧2断言已暴露并要求同步；P3覆盖项仍跟踪 |
| 10 | 工程一致性 | 标题、文案、a11y 残余 P3 见清单 |
| 11 | 数据与事务 | 本批不改存储；离页不发迟到取消、查询不重发验证保留 |
| 12 | 依赖治理 | 修复未新增依赖；UI-08 原新增依赖整体审查不在此增量内 |

## 5. 整改清单

12 项 P3 以本报告表格中的稳定 ID 登记；负责人：后续 UI 维护实现者；迭代：UI-08 后续润色/P1 页面同步，具体排期由台账维护。没有以 P3 豁免未修 P2。整体验收仍需 workbench/repairs 与 analysis 独立复审。

## 6. 架构防腐与长效治理建议

1. 目录失败、旧值和成功值的转换保留独立自动测试，避免新的全局状态组件又隐藏读取失败；成本为现有4例维护。
2. CLI 展示命令保持单一来源且使用真实 parser 校验；新增案例入口时同步其测试，不将UI文字领先于程序。
3. 浏览器后退、手机返回列表与选择状态纳入针对性门禁，修复DOM语义时同步按角色定位的测试。

## 7. 审计声明

本报告只对所列修复点及当前指纹有效；不等同完整 UI-08 验收或生产上线许可。未改生产代码；无豁免。下游 schema2 整合需单独复核其影响；真实模型效果由独立实验报告证明，不能引用本报告代替。

### 本轮文件指纹（schema2整合前）

| 文件 | SHA-256 |
|---|---|
| `frontend/lib/environment.ts` | `a30e89dc29da13073963adf2088ae94d54fc6d787de872e52d2bddaa02c489e6` |
| `frontend/components/environment-status.tsx` | `3b670d1a7f0486893fa08a4dc7ba538c99439963e7b3816050751827a2f7f69e` |
| `frontend/components/app-shell.tsx` | `88c2c31d5152976e8745cfb57f1d48886c353e0d44cb9d0a7fccc0263933b029` |
| `frontend/components/overview.tsx` | `8568b8287cf791109a5e75596d26c1cf428ca2e8442e54dfd5b421484521be0d` |
| `frontend/components/ui/confirm-dialog.tsx` | `8a9761e835d92d117addf65f5ff9c01c977019007e2547154206428a748db4b5` |
| `frontend/components/ui/page-header.tsx` | `a78c94e7b83f82e6e1e184f1734dc1668b7b6e3b20d1194444b8436608d2a2ad` |
| `frontend/components/environment/status-section.tsx` | `e437257e9213af7e162fcf1093397f08adaf6e7b2f8bdafa0e7faf5eb6f2ee68` |
| `frontend/components/environment/model-section.tsx` | `2c2508aa67c86f481de75fb4127a6516cac0dd7fbdac46a0aa7adbe023d4573b` |
| `frontend/lib/format.ts` | `11092893b58f66cd17403ab1be69df863b95bd7674497ef83033e35f8a7575af` |
| `frontend/app/styles/foundation.css` | `7b05607424ff76ac6b34bd7d33ed2813b9bc107fe58fa4c23ce4414343e3926f` |
| `frontend/components/run-history.tsx` | `09c04002d21ff2d46663f7fdddb1666fc612345b835facd2e80122141b53cb37` |
| `frontend/components/run-detail.tsx` | `ea20c28397acff7ade8a143d518670599a33f08d753de80299cfac218bea4325` |
| `frontend/components/reproduction-panel.tsx` | `a392182482b581c33689bb2949afc395f7b11a78df22bec5be57bf0b8e17fb23` |
| `frontend/lib/reproduction-result.ts` | `0c1d215b66ed172854496427a68bdb120998ed8186474479654119e1c097adb8` |
| `frontend/app/page.tsx` | `5953750d1a80198c8e0b14a4b35682ccb47b520ef9324c040448c4f2266f771f` |
| `frontend/lib/repairs.ts` | `f5c22689a96b27ee568163c19169d319a9b7cb3f1c3c4f81e639dbd962134a12` |
| `frontend/lib/milestones.ts` | `595d42311bd6da76d9c5b444c2d41d6e228736331b1abe0e8ecc133b6ca6b6bf` |
| `README.md` | `6a4310c63f7c2bb2541e4d80cfc425a7d37535f333efc7c149e40aa1da4bffa1` |
| `docs/27-local-development-guide.md` | `5067f3c951cb2c75a419e3b71d0845512e180dc3c038a435469453fa8f70a1c1` |
| `frontend/tests/runs.spec.ts` | `1de119f2936a7ec3dffc51617608e95c34fec80d46adc0c2eff0628eae99e324` |
| `frontend/tests/ui08-review-fixes.spec.ts` | `0b1e956037ed4116aa8c42ab3a5d09fab3af71aef95badc37803d166257f007c` |
| `frontend/tests/ui08-shell-followup-independent.spec.ts` | `444e8616af0c00df4fbe5055b4d0e5a51a92379531fc9d5dc97c8a940b74f0d3` |
| `tests/test_frontend_cli_commands.py` | `6d4c61bfa3134c1ab17f21c755b5efa64a5d0637a283c76427803e09101c32f8` |
