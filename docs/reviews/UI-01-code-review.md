# UI-01 独立代码评审与验收

日期：2026-10-13。实现 `/root`；API 专职 reviewer `/root/review_ui_api`；前端专职 reviewer `/root/code_review_m0`。评审均只读，修复由实现者完成，之后独立复审。

## 范围

产品首页、七个工作区入口（真实检查 + 六个交互预览）、本地 FastAPI 适配、配置、测试与依赖。UI 先交付，真实 Agent/MCP/记忆持久化未实现，不在通过范围内。

前端使用获授权的 frontend-design / web-design-guidelines 技能；最新界面规范已读取。后端按 auditing-enterprise-code-quality 检查边界、生命周期与契约。

## 发现、修复与复审

| ID | 严重度 | 问题 | 修复及独立复审 |
|---|---|---|---|
| API-01 | Defect P1 | HTTP取消提前释放槽，后台检查仍运行 | 独立worker持有槽、finally释放、shutdown等待；连续取消/异常/429/可复用测试通过 |
| API-02 | Defect P2 | Host中间件返回纯文本与JSON契约不符 | 统一固定JSON host_forbidden；状态和no-store实测通过 |
| UI-01 | Defect P1 | TextDecoder默认删除BOM，证据被改变 | ignoreBOM:true；实测首字符65279，E2E验证发送字节相同且拒判 |
| UI-02 | Defect P1 | 内部跳转绕过beforeunload，草稿丢失 | Link导航确认、标签页内存草稿；取消跳转和Back/Forward恢复独立验证 |
| UI-03 | Defect P2 | 390px手机布局被侧栏撑宽至490px | sidebar min-width:0，局部导航滚动；16个页面/视口组合均无整页横向溢出 |
| UI-04 | Defect P2 | 辅助文字对比不足 | 调整文字色；16次axe WCAG2A/AA均零违规 |
| UI-05 | Defect P2 | `section in modules`接受toString等继承键 | Object.hasOwn，非法模块实测404 |
| UI-06 | Defect P2 | 测试标签同时匹配section和textarea | 改textbox角色定位；9项项目E2E通过 |

复审结论：API、前端当前范围均 Pass，未发现未解决 Defect P0/P1/P2。原取消路径的失败测试未删除；它验证了修复有效性。没有通过风险豁免跳过阻断项。

## 实际验收

- Python：99 项通过（含 13 项 API 测试）；Ruff、mypy 通过。Starlette/httpx 测试适配有弃用警告，记录在依赖文档。
- 前端：TypeScript 与 Next production build 通过。
- `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`：**9 passed**。真实首页→API→报告、编辑失效、非法输入、数字和重复键、断网恢复、六模块交互、BOM、草稿导航与非法路由。
- 8页 × 1440/390px：axe WCAG2A/AA无违规；独立reviewer另运行16次检查得到相同结果。自动扫描不等于完整WCAG认证。
- API reviewer额外验证取消请求后立即关闭lifespan：关闭等待worker，完成后槽释放。
- `uvx pip-audit`、`npm audit`：当前环境0条已知漏洞；范围见06。
- 远端GitHub Actions配置已加入frontend job；尚未推送/远端执行，不能把本地通过写成CI已经通过。

## 运行与视觉证据

本地（忽略、不入Git）：

- `artifacts/ui-home-1440.png`、`ui-home-390.png`：产品首页，已实际看图。
- `artifacts/ui-check-desktop.png`：真实检查失败及字段证据。
- `artifacts/ui-review-final-axe.json`、`ui-review-fixed390.png`：reviewer独立布局/可访问性证据。
- `artifacts/dependency-audit-ui.json`、`npm-audit-ui.json`：当前依赖公告扫描。

审查关键快照（格式化后）：

```text
api.py 46b0d0c329a0a3e7b21b41f11548dd6779445c90f4a18336c3a92d6f9b94240c
test_api.py 7c63d43b87acd37829269dec97e200896ed845f817e5cca13155c43e1d6484ea
frontend/app/workbench/page.tsx 16f6848636d204ee20e6fb78a11d909504279229d000cc1e92484af9d9c0c774
frontend/components/sidebar.tsx 75962569a3c1b10339e0c51cbd6b6459e86489b6010a6ba6e00a43470f0013bc
frontend/app/globals.css fd7acee34c9fae25903db2bd357c656682bc3a6792940a42933dfa6d66f92e24
frontend/tests/product.spec.ts 54be9c88a30dd4e20ae1e932ce3bc50a49aaf0ec60c7105b3d58e24be7e27e41
```

## 限制

当前只验证本地单用户环境与Chrome。未做Safari/Firefox、真实读屏器、真实触控设备、公网/多租户发布测试。预览不执行模型/命令、不保存连接或项目记忆。品牌名和最终logo仍待产品命名决策，当前为工程代号标识。
