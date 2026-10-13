# 企业代码质量审计：UI-04 导航层级调整

- **范围**：侧栏产品说明迁移到主内容底部，共用 WorkspaceFooter，工作台离开保护与相关 CSS、测试、文案、docs16；不重新审P0-04完整任务页。
- **版本**：2026-10-13 独立副本 `<review-workspaces>/ui-04-review`，SHA清单见 `UI-04-snapshot.json`。
- **技能**：auditing-enterprise-code-quality；frontend-design用于对照两阶段设计与用户要求。
- **场景/严苛度**：General SaaS / Mission-Critical。

## 1. 代码质量评估卡

**100 / 100，范围内 Pass。** 初轮1项Defect P2（97分）已修复并完成独立运行复核，剩余P0/P1/P2/P3均0；100−0=100，无封顶。此结论只覆盖UI-04，不代表全产品上线认证。

## 2. 事故风险推演

无P0/P1。实际复现的P2影响语义与测试：原footer嵌在main内，浏览器不暴露contentinfo；新增按contentinfo查找的测试超时。内部具名navigation仍可访问，不将此误报为整个导航不可访问。

## 3. 详细审计明细

### P0

none。

### P1

none。

### P2 — UI04-R01：嵌套footer与测试预期角色不一致

- **位置**：`frontend/components/workspace-footer.tsx:10`；`frontend/tests/appearance.spec.ts:115`、`frontend/tests/product.spec.ts:185`（修复前相同行）。
- **维度/置信度**：8语义契约、9可测试性；[confirmed]。
- **证据**：真实3010 Chrome页面 `.workspace-footer`=1，`getByRole("contentinfo", {name:"产品信息"})`=0；独立最小HTML `<main><footer aria-label="产品信息">…</footer></main>` 同样为0。父任务第一轮16通过、2失败与该路径吻合。
- **修复**：main内使用具名section，自然暴露region；两测试改按region定位。保留内部nav语义，不强行嵌套全站contentinfo。
- **状态**：closed：section具名region和修改后的定位均经真实Chrome验证，四组合region=1、axe0。

### P3

none。

## 4. 维度覆盖声明

| # | 维度 | 结论 |
|---|---|---|
| 1 | 架构边界 | 共用页脚组件，侧栏保留工作模块；符合用户指示 |
| 2 | SOLID | 共用beforeNavigate回调，无重复草稿逻辑 |
| 3 | 并发资源 | 无新增网络/定时器/并发资源；不适用 |
| 4 | 容错 | 两条链接取消离开均保留原草稿，未改变既有beforeunload |
| 5 | 性能 | 两个静态链接，无新增依赖/昂贵动画 |
| 6 | 安全与合规 | 不新增外发或执行权限；页脚范围axe四组合0 |
| 7 | 可观测性 | 保留迭代历史，完成独立复核后UI-04才标已完成 |
| 8 | 类型与语义 | R01角色不匹配已修复，真实Chrome四组合均通过 |
| 9 | 可测试性 | 原失败可复现，测试修正为真实语义；新增草稿路径 |
| 10 | 工程规范 | docs16包含设计/自审/实现边界；实现未扩大到重设计 |
| 11 | 数据完整性 | 草稿guard两链接复用同函数；没有新增数据写入 |
| 12 | 依赖供应链 | 无package依赖改动，复用既有构建链 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| UI04-R01 | Defect P2 | root | UI-04标done前 | closed：源码及真实浏览器复核通过 |

## 6. 长效治理建议

1. 功能工作区辅助信息继续复用单组件；在具名nav/region中定位测试，避免依赖错误的隐式landmark假设。
2. 保留两条辅助链接的草稿取消回归；新内部链接接同一beforeNavigate。
3. 保留CSS末端明确作用域覆盖：footer nav的flex、margin0、gap覆盖全局nav及900px规则；新增样式不再使用无作用域nav覆盖。

## 7. 审计声明

只读审代码，未格式化或编辑实现。浏览器使用真实3010页，使用主项目已安装Playwright/Chrome读取页面，截图在独立 `artifacts/ui-04-review/`；未重新安装依赖或停止服务。独立浅/深×1280/390组合均无横向溢出，nav为flex/margin0、链接12px/高度44px，页脚范围axe0；dark-390截图人工检查符合轻量辅助信息层级。两条辅助链接dismiss后原草稿不变。上述为修复前样式与guard证据，修复后region验证另补。父任务负责production build/typecheck与原测试结果，本报告不会冒称那些命令由独立reviewer运行。完整站点重设计、后端及其他未变模块不在本批范围。

## 修复后独立复核

真实3010新构建，浅/深×1280/390四组合均：具名region=1、页脚axe0、键盘Enter打开迭代页、焦点outline solid；减少动效时链接与伪元素transition均0s。两条辅助链接取消离开保留原草稿，接受产品介绍确认后进入首页。UI04-R01关闭。父任务报告新build/typecheck通过；原16pass/2fail保留为初轮记录，修复后定向回归另记，不合并成虚构的全量通过。

最终父任务证据：初轮16pass/2fail→修复后定向8passed（16.2s，原失败2+浅深/布局axe6），production build/typecheck通过。仅milestones状态调整中→已完成的文字增量已精确比较并纳入SHA；docs03/16已同步。没有把重叠用例相加成24个独立测试，没有再次运行后端。
