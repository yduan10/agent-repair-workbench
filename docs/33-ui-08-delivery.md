# UI-08：产品界面整合验收

2026-10-15。状态：planned → ready → in_progress → in_review → done。保留用户确认的中性工程风；本次不重新设计视觉方向。验收范围是 UI-08 及与 P0-06 schema2 的局部整合，不是任意项目修复能力证明。

## 1. 交付内容

- 共用外壳、总览、环境状态、浅深色主题、CodeMirror 调用证据编辑器；文档/更新记录置于辅助导航。
- 修复页合并代码差异与回归标签，技术标识折叠；记录、候选和标签写入 URL。
- 环境请求失败不沿用旧的绿色就绪状态；部分记录读取失败不冒充空库。
- 运行场景的执行状态与预设故障观察分别显示；终端的其他场景不套用四种网页示例的预期。
- 历史通过保持中性「记录为通过」，只有当前证据核验通过才显示绿色结论。候选证据撤回跨标签和候选切换保持，不能借另一候选的视图恢复失效结论。
- 修复记录新增明确案例名称：返回类型错误、计数值偏移。只读 API list/detail 升级 schema2；comparison/diff 保持 schema1。这个接口增量属于 P0-06，已单独评审，不把 UI-08 的「不改 API」约束当作可忽略规则。

## 2. 验收证据与失败保留

| 门禁 | 实际结果 |
|---|---|
| TypeScript / 生产构建 | typecheck、最终生产构建通过；新增文档路由已生成 |
| 初次完整浏览器 | 180 passed / 9 skipped / 1 failed；唯一失败为构建后新增评审文档路由未生成；最终重建后完整重验181 passed / 9 skipped / 0 failed（3.2分钟） |
| 原 UI-08 缺陷复审 | shell/runs/public 原9项P2闭合；core 原P1及分析P2闭合；新增多候选反例修复后通过 |
| schema2增量 | 20项独立数据契约检查；32项生产浏览器回归通过，含BOM导航、候选正反对照 |
| 真实网页执行 | 隔离数据库实链路3 passed / 1 skipped（模型项）；覆盖检查、证据阅读、正常/工具错误Docker；当前真实模型另见P0-06实验 |
| 真实修复读取 | 两案例12条记录的案例契约与选中候选真实diff/回归，2 passed；不把标签检查等同全12个diff验证 |
| 用户数据 | 沿用主库，不迁移、不清空，不灌入验收任务；所有写操作测试使用独立数据库 |

先前失败不删除：dev模式的Next浮层曾阻挡BOM导航，切生产后通过；两项旧运行测试仍要求旧导航行为，更新为URL自动选中/返回按钮后17项重跑通过；case标题变化后旧角色名选择器改为task链接+案例名；真实执行测试更新为等待本次POST接受的ID，避免读取上一条报告。测试结果不能相加当作互不重复的用例总数。

独立报告：

- [外壳/运行/公开页面复审](reviews/UI-08-shell-followup-review.md)
- [检查/分析/修复复审](reviews/UI-08-core-followup-review.md)
- [schema2增量复审](reviews/UI-08-schema2-integration-review.md)
- [真实修复读取复审](reviews/UI-08-real-repair-followup-review.md)
- [真实网页控制台复审](reviews/UI-08-live-console-followup-review.md)
- [网页分析边界增量复审](reviews/P0-06-web-admission-integration-review.md)

## 3. 剩余小缺陷登记

以下均为已评审 Defect P3，负责人为前端维护者，迭代归入 P1-01 界面维护；不作为已修复项。具体复现、位置和建议以链接报告为准。开始相关组件下一轮变更时先处理对应项，并补反例；如影响扩大，重新分级。

| 跟踪组 | 原报告编号 | 内容 |
|---|---|---|
| UI08-S | shell D9/D10/D12/D13/D15 | 错误页恢复与全局错误页、端口文案、手动主题的theme-color、接入页能力口径、PathTrail语义 |
| UI08-R | runs D6/D10 | 不存在的待确认请求放弃入口及相关覆盖 |
| UI08-P | public D3/D5/D6/D7/D8 | 首屏链路文案、容器参数/退出码措辞、文档标题元数据、landmark命名、真实checker测试争用 |
| UI08-C | core D3/D4/D5/D6/D8/D10 | textarea回退换行、错误提示细分、异常diff头、Unicode行内差异、同页导航、针对性覆盖 |
| UI08-A | analysis AN03–AN11 | 关联运行标签/过滤、事件语义、未知结果提示、证据展开状态、429提示、列表/滚动等细节；AN07部分已修 |

本轮闭合原shell/runs/public共9项P2、原core阻断项及新增D2-M；没有以剩余P3掩盖未关闭P0/P1/P2。

## 4. 后续开发约束

继续复用 `foundation.css`、共享UI组件、紧凑记录列表、结果优先与技术详情折叠；动效回应用户操作。P1-01将在既有修复页面接入开始/停止/候选接受，不新建一套大卡片导航。模型费用未知时保持未知；未接受候选不能显示已写回。轨迹对齐与确定性差异归因仍需单独规格，当前代码差异视图不代表该引擎已经实现。


## 5. 验证命令与材料

在 `frontend` 目录：

```sh
npm run typecheck
npm run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test --output ../artifacts/ui08-final-e2e-results --reporter=line
```

默认浏览器suite对实链路门禁使用显式跳过。单独实链路需独立初始化数据库与API：console设置 `AWB_CONSOLE_LIVE=1`、`AWB_STATE_DIR` 指向独立 `awb-console-live-*/state`，服务8034；repair设置 `AWB_REPAIR_CASES_LIVE_URL` 和 `AWB_REPAIR_LIVE_URL` 指向只读实验API8035。详细命令见对应独立报告；不把测试服务地址当用户正式配置。

材料：`artifacts/ui08-final-build.log`、`artifacts/ui08-final-e2e-rerun.log`、`artifacts/ui08-real-repair-review`及各独立报告。首次失败日志继续保留。

最终交付文档独立复审：[交付审核](reviews/P0-06-UI-08-delivery-review.md)。UI-08按上述范围完成；第3节27项P3仍属后续维护，不宣称全部细节缺陷已消失。
