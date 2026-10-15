# UI-08 / P0-06 schema2 集成独立增量评审

- 审计对象：`frontend/lib/repairs.ts` 契约嫁接；`repair-workspace.tsx` / `overview.tsx` 的案例标签；对应测试 fixture 升级。仅本次约百行集成增量，不重新评整个 UI。
- 基线：已评审 `<review-workspaces>/p006-heldout/frontend/lib/repairs.ts` + `UI-08-core-followup-review.md` 的 D2-M 修复后主目录。
- 版本：HEAD `802bf70` 加 2026-10-15 工作树；最终摘要见本地 artifacts。
- 技术栈：TypeScript / React / Zod / Playwright。
- 场景 / 严苛度：General SaaS / Mission-Critical。
- 时间：2026-10-15，Asia/Shanghai。

## 1. 代码质量评估卡

增量复审 **Pass**：未发现新增 P0/P1/P2/P3；生产浏览器定向门禁通过。

| P0 | P1 | P2 | P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 (仅集成增量，不含已跟踪15项P3)
VERDICT: Pass — 20 schema checks and 32 production-browser targeted tests passed
NOT ASSESSED: real model repair and host sandbox, outside UI merge scope
```

## 2. 生产事故风险推演

P0/P1：none。

需要协调部署：列表/详情的外层 schema_version 为 2，旧前端与新后端混用会安全拒绝读取。此次 API 与前端由 root 协调停止、重建、恢复，不需要修改真实用户记录。比较报告、快照与 diff 的内层版本仍是 1。

## 3. 详细审计明细

### P0/P1/P2/P3

本次窄增量 none。既有 P3 在 `UI-08-core-followup-review.md` 跟踪，不因本报告而清除。

### 已核对的实现与不变量

1. 与已评审 sandbox 的逐行差异中，所有 zod strictObject、refine、输入上限和关联约束一致；没有放宽以兼容错误数据。
2. `task.case_id` 仅允许 `output_mismatch` 和 `counter_offset`；没有任意字符串回退。
3. detail/list 外层版本必须 2；旧版本被拒绝，diff/comparison/snapshot 保持版本 1。
4. 当前通过的第一槽必须复现案例自己的指纹：类型错误对应 `count_type`，偏移对应 `count_value`。不会把二者当通用可接受集合。
5. detail refine 先验证 `slots.length === 4` 再访问槽位，缺0/1/3槽不会抛未捕获 TypeError。
6. 实际 UI 标题、修复行和 overview 活动名统一来自校验后的 `case_id`；保留模式信息，不从低层 wrong_type 场景猜类型。
7. D1 修复保留：摘要中的历史通过仍 neutral “记录为通过”，只有当前详情核验后显示“回归通过”。
8. D2-M 修复保留：全部已撤回候选按 task ID + summary SHA 绑定，标题、行与候选导航共享集合；切候选不会清除记录。
9. `loadDiff` 的新增错误分流仅区分结构错误和关联错配，task/candidate/tree SHA 核验没有改变。
10. 未新增浏览器写请求、模型配置入口或人工接受行为；本次 UI 仍只读修复记录。

### 运行证据

- 审计者重跑 `node tests/repair-case-schema-review.cjs`：原样输出 **`20 independent schema checks passed`**。这是 synthetic DTO 单元验证，不是服务端或模型运行。
- 新增独立浏览器例：计数偏移名称贯穿列表/详情/总览；总览仍显示历史通过；故意只把 task 改回 output_mismatch 后，计数值指纹被详情拒绝。
- 生产3010 + 真实8030下运行 `PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/repairs.spec.ts tests/ui08-core-independent.spec.ts tests/product.spec.ts --trace off`：首轮 **`31 passed, 1 failed (38.8s)`**，唯一失败是旧测试仍定位“三角色修复”链接。审计者仅将该选择器更新为 task URL，并显式断言新案例文字，未改生产代码。全组重跑 **`32 passed (29.3s)`**。
- 其中 repair 响应都是 mock，覆盖两案例标签/交叉指纹、D2两个正反例、历史通过、深浅色与手机布局；product 使用真实 `/api/check`。BOM导航保护生产模式两轮均通过，未隐藏浮层或强制点击。
- 新 `repair-cases.spec.ts` 真实临时SQLite/API双案例测试本轮未执行，等待 root 提供临时数据；这不作为当前32项的组成。
- 文件摘要：`artifacts/ui08-schema2-integration-sha256.json`。

## 4. 维度覆盖声明

| # | 维度 | 发现 | 说明 |
|---|---|---|---|
| 1 | 架构与边界 | none | 仅只读 DTO 与展示 |
| 2 | SOLID | none | 沿用既有标签映射 |
| 3 | 并发与资源 | none | 未改请求生命周期，D2集合仍绑定任务 |
| 4 | 容错 | none | malformed slots 安全拒绝 |
| 5 | 性能 | none | 无新增轮询或请求 |
| 6 | 安全合规 | none | 无原始模型/私有数据新增外发 |
| 7 | 可观测性 | none | 不兼容响应有明确提示 |
| 8 | 类型契约 | none | strict schema2 与 case 指纹 |
| 9 | 可测试性 | none | 独立20契约反例与浏览器正反例 |
| 10 | 工程一致性 | none | UI08风格与中文标签保留 |
| 11 | 数据完整性 | none | 不改记录，不伪造当前通过 |
| 12 | 依赖治理 | none | 没有新增依赖 |

## 5. 整改清单

无新增产品缺陷。陈旧测试选择器已修复并复跑；真实临时双案例读取由后续数据验收补充。

## 6. 长效治理建议

- API 版本升级保持前后端共同契约反例，尤其是“合法 schema + 错误案例指纹”。
- 修复摘要的历史结论与详情当前核验继续分离，未来新案例沿用同一条规则。

## 7. 审计声明

审计者未修改生产文件；新增独立测试不调用模型，不创建用户修复任务。本报告只覆盖 schema2 手工集成增量，不能替代 P0-06 真实12次模型实验、容器回收和整体交付验收。
