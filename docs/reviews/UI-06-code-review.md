# 企业代码质量审计报告：UI-06

- **审计对象**：站内工程文档阅读器、文档导航与相对链接、主题布局及依赖增量。
- **版本**：工作区快照；文件清单见 `UI-06-source-sha256.json`。
- **技术栈**：Next.js / React / TypeScript / react-markdown 10.1.0 / remark-gfm 4.0.1 / Mermaid 12.2.0 / Playwright / axe。
- **业务场景**：General SaaS。
- **严苛度**：Mission-Critical。
- **时间**：2026-10-13。
- **独立性**：评审者未实现本批功能，只在独立副本写入探针和报告；复用本地已构建页面，不操作生产源码或服务生命周期。

## 1. 代码质量评估卡

- **得分**：首轮 97 / 100；修复复审后 **100 / 100**，仅评价本批范围。
- **门禁结论**：**Pass / UI-06 合入通过**。
- **范围**：13 个前端文件（含新图表组件及本报告随附的 7 项独立探针）；页面阅读器、文档读取/导航库、文档首页、UI-06 CSS、依赖清单/锁文件、相关测试与历史状态。
- **范围内未评估**：none。
- **范围外**：模型执行、后端授权、公开发布及远端 CI。这些不由文档阅读器实现，本报告不计为其验收完成。

| 级别 | 首轮确认 | 修复复审后未关闭 |
|---|---:|---:|
| P0 | 0 | 0 |
| P1 | 0 | 0 |
| P2 | 1 | 0 |
| P3 | 1 | 0 |

```text
STRICTNESS:   Mission-Critical
SCENARIO:     General SaaS
INITIAL:      100 - P2×1×3 = 97; P2 budget=0 → Fail
MERMAID:      P2-1 closed; new P3-1 open → 99 / 100
FINAL:        P2-1 and P3-1 closed; deductions=0; cap=none → 100 / 100
VERDICT:      Pass — 已确认问题关闭，本批独立验收通过
NOT ASSESSED: none within declared scope
```

### 独立证据

```text
PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/document-reader.spec.ts tests/reviewer-document-reader.spec.ts --reporter=line
{"pages":50,"localLinks":47,"broken":[]}
14 passed (13.5s)

npm run typecheck
> tsc --noEmit
(exit 0)

npm audit --omit=dev --json
"vulnerabilities": {}
"total": 0
(exit 0)
```

- 修复后的 7 项实现方用例 + 7 项独立探针通过。前者验证站内阅读/返回、交叉引用、未登记路径、3 文档 × 4 主题/视口组合的无整页溢出和 WCAG 2 A/AA；后者补全量文档及键盘行为。
- 独立遍历当时登记的 50 个 Markdown 页面：TOC 锚点存在、DOM ID 不重复；47 个正文站内文档链接均成功（此前纯阅读器阶段为45个，随文档更新增加）。伪文件、编码路径穿越和未登记评审路径返回 400/404。
- 手机键盘可展开本页目录并跳至章节；表格 focus 后 ArrowRight 实际增大 scrollLeft。浅色桌面与深色手机截图人工检查正常：`artifacts/ui06-light-1440.png`、`artifacts/ui06-dark-390.png`。
- 构建 trace 文件共 204 项，包含 49 个 docs Markdown；没有 `.env`、`.git`、SQLite、artifacts、虚拟环境条目。README 为单独固定读取。该检查不代表对任意未来构建产物的永久保证。
- 源码确认：路由只匹配已登记的文档；不使用请求 slug 构造文件路径；目录遍历不跟随符号链接目录；Markdown 不启用原始 HTML/MDX，普通 Markdown 图片组件输出替代文字而非 img，未注册任意插件加载器。新增仓库架构图使用惰性渲染后的 data SVG img，不允许文档远程图片；图表源不来自用户上传。
- npm audit 仅表示当时注册表对生产依赖无已知公告，不保证依赖不存在未知漏洞。

### Mermaid 增量与复测说明

- 固定 Mermaid 12.2.0；生产依赖公告再次扫描仍为0；TypeScript通过。
- 实际架构图文字和箭头可读，横向滚动限制在图区；源码始终可展开。无SVG innerHTML注入，普通正文不启用raw HTML/MDX。
- 独立浏览器负例将页面中的 flowchart LR 临时替换成不支持的 flowchart XX：展示源码回退，不发出外站请求。只改当前浏览器响应，没有修改文档或服务。
- 快速 light/dark 切换的最终 SVG 样式与最终主题一致，输出无 script/foreignObject；近景截图 `artifacts/ui06-diagram-closeup.png` 人工确认文字清楚。
- 审查环境曾把新增的未发布报告混入文档枚举，以及把 node_modules 备份留在 TypeScript 扫描目录，分别造成额外404和内存耗尽。已移出审查产物/备份后复测通过；不是生产缺陷，未靠排除生产文档或扩大堆限制掩盖。
- 上述50页是当时构建的实际集合；本报告及公开审计文档加入后，最终构建/CI须按探针重新枚举，不固定页数。

## 2. 生产事故风险推演

none。未确认 P0/P1。

## 3. 详细审计明细

### P0 — 阻断性缺陷

none。

### P1 — 严重缺陷

none。

### P2 — 主要缺陷

#### P2-1. 手机目录测试同时命中隐藏桌面标题（已关闭）

- **位置**：`frontend/tests/document-reader.spec.ts:42`。
- **维度**：可测试性与工程门禁。
- **置信度**：confirmed。
- **问题**：`getByText("本页章节", {exact:true})` 同时命中可见 summary 和隐藏桌面 span，Playwright 严格模式拒绝点击。浅深手机两项固定失败，导致本批浏览器门禁无法通过；不是用户交互本身失效。
- **首轮独立结果**：4 passed / 2 failed，错误为 `strict mode violation`，两个目标分别为 summary 与 span。
- **最小修复**：改为 `.document-mobile-toc summary`，保留展开后导航可见断言，未删除或放宽行为验证。
- **复测**：修复后两项手机用例通过，另补真实键盘 Enter 展开与锚点跳转。当前 closed。

### P3 — 次要缺陷

#### P3-1. Mermaid 12 的非 HTML 标签设置未生效（已关闭）

- **位置**：`frontend/components/document-diagram.tsx` 的 mermaid.initialize 配置。
- **置信度**：confirmed。
- **问题**：仅设置 flowchart.htmlLabels=false 时，实际 SVG 仍含 foreignObject；与设计中的非 HTML 标签约束不一致。图表始终作为惰性 img 展示，此问题未判定为 XSS。
- **修复**：补顶层 htmlLabels=false，保留 strict、源语法限制和惰性图像展示。
- **复测**：解码真实 img.src 后无 foreignObject/script；浅深色、快速连续切换最终 SVG 主题及源码兜底均通过。当前 closed。

## 4. 维度覆盖声明

| # | 维度 | 发现 | 结论 |
|---|---|---|---|
| 1 | 架构与边界 | none | 构建时登记仓库文档，正文与源码同源；用户访问参数不直接转换为文件路径。 |
| 2 | SOLID 与现代设计 | none | 文档读取、URL 映射、导航数据与渲染分离，延续已有产品主题。 |
| 3 | 并发、异步与资源安全 | none | 正文静态；Mermaid共享配置通过渲染队列串行，主题revision与卸载标记保护状态写回，快速切换已实测。 |
| 4 | 容错与防御性编程 | none | 未登记路径404；危险协议和绝对路径不渲染为可点击目标；不载入远程图片；只允许本地图表 data SVG。 |
| 5 | 性能与计算效率 | none | 50 个已登记页面的构建/读取有界，正文静态输出，无新轮询或模型调用。 |
| 6 | 安全与数据合规 | none | skipHtml、无MDX/raw HTML插件、文字渲染、外部链接noopener/noreferrer；trace没有私密运行文件。 |
| 7 | 可观测性与运维友好度 | none | 本地目录与源码入口明确区分；历史规格保留当时范围，不宣称模型执行已完成。 |
| 8 | 类型安全与契约表达 | P3-1 closed | 类型检查通过；Mermaid顶层配置已按真实SVG验证，slug与文档集合精确匹配。 |
| 9 | 可测试性与死代码 | P2-1 closed | 首轮定位歧义已修复；全量TOC与交叉链接、拒绝路径、键盘探针补充已有12组视觉/axe覆盖。 |
| 10 | 工程规范与一致性 | none | 标题/正文/列表/表格/代码/焦点沿用主题；正文独立页面、移动目录与继续阅读可达。 |
| 11 | 数据与事务完整性 | none | 没有存储写入；构建读取真实Markdown，不维持第二套手写正文。 |
| 12 | 依赖与供应链治理 | none | 新依赖固定版本并锁定；无生产依赖公告；构建trace未扩散到运行目录。 |

## 5. 整改清单

| ID | 级别 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| P2-1 | P2 | UI-06 实现者 | 本批完成前 | closed |
| P3-1 | P3 | UI-06 实现者 | 本批完成前 | closed |

## 6. 架构防腐与长效治理建议

1. **全量导航探针**：文档源新增后继续检测登记页面、TOC ID 与站内文档链接，成本为当前约数秒的本地只读测试，防止正文和导航集合漂移。
2. **维持仓库文档信任边界**：未来若引入用户上传/远程 Markdown，另行加入文件、体积、深度、URL 与插件策略评审；当前固定仓库内容的结论不能直接扩展到任意输入。

## 7. 审计声明

- 已施加豁免：none。
- 范围内未评估：none；公开发布与远端 CI 由相应门禁单独确认。
- 本报告仅对所列源码快照有效，后续文档集合扩大或 URL/渲染策略变化需增量审查。
- 最终状态已静态复核：UI-06 done、阅读/图表验收和未接通模型边界一致；远端CI未提前宣称本提交通过。
- 源码清单 SHA-256：`4facdaa92a0020d0cc057a5d897e71c92ce53854a5a6fa58c1d5acfab56572f0`。独立探针使用随附版本，合入后与本清单核对。
