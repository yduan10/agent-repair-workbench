# README 与本地指南独立复审

2026-10-14；final_review 独立只读实现与文档，未参与这两份文档改写。范围仅 `README.md`、`docs/27-local-development-guide.md`；方法为 auditing-enterprise-code-quality，General SaaS / Mission-Critical。快照见文末。

## 1. 质量评估卡

**Pass，100/100。** 首屏明确目标用户、输入、产出和边界；最短体验不要求模型/Docker；高级启动与验收移入指南。P0-06仍为设计阶段，未宣称补丁应用或自动修复已交付。无待修P0/P1/P2/P3，无范围内未评估项。

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass (two documentation files only)
```

## 2. 风险推演

无残余阻断。已修正文案可能造成的两项误判：把元数据核对误认为候选正文审查；把跳过T05的命令当作完整容器门禁。

## 3. 明细与验证

- README第74行已改为注册证据与候选元数据核对，明确建议正文未交给验证角色、未执行。不存在“验证Agent已证明修复”的当前能力暗示。
- 指南第122行增加 `AWB_TOOL_DOCKER=1`，不遗漏当前三项真实T05门禁；默认跳过不计通过。
- clone地址匹配项目origin；本地相对链接与README/指南锚点逐一解析无缺失。核对站内 `docs.server.ts` 规则：根README映射 `/docs/getting-started`，docs/README映射 `/docs/index`，新指南映射 `/docs/27-local-development-guide`；非文档源码链接按既有机制跳源码仓库。
- 独立实跑README示例（已安装锁依赖环境，不冒称全新机器安装验证）：

```text
uv run --frozen agent-workbench check examples/failing.json
exit 1, status failed
uv run --frozen agent-workbench check examples/passing.json
exit 0, status passed
```

同时断言失败规则为 `output_schema_violation`、路径 `/result/structured_content/count`，与文档片段一致。未开启模型或容器，未修改数据库。

## 4. 维度覆盖

| 维度 | 结论 |
|---|---|
| 架构/边界、职责、工程规范 | 产品介绍与操作指南分离；当前/计划明确 |
| 类型/契约、可测试性 | 命令退出码/关键字段独立核对，相对链接与锚点有效 |
| 安全/容错、可观测性 | 凭据不入命令；未知状态、预算、恢复限制保留 |
| 并发/性能、事务 | 本批无执行逻辑修改，相关操作说明保持现有约束 |
| 依赖治理 | 无新依赖；安装使用锁定环境，许可证边界保留 |

## 5. 整改清单

两项初评文案偏差均已关闭；无豁免。

## 6. 维护建议

每次功能交付同时更新首屏能力及指南命令；完整门禁新增显式开关时同步指南，避免历史命令被继续标作全量。

## 7. 审计声明

本结论仅为文档清晰度、可执行说明与当前边界复审，不替代P0-06设计/实现、模型效果或市场验证。未重新安装全部依赖，未启动服务或build；这些非本次文档变更范围。修改后的文件需增量复核。

```text
12995501a5b806cf7dbcab831d07b1919f2d1616f4d04fd54b46639fcb4bee00  README.md
2305fe270d84f457c4fe4e49d4d39fcab276a2a9977398928e7724e8c98a6571  docs/27-local-development-guide.md
```

## 8. 导航增量复核

2026-10-14，增量范围仅 `frontend/lib/documentation.ts` 两个入口文案及指南入口、`docs/README.md` 新增 26/27 索引行。标题与内容一致，原 getting-started 路由保持，新指南 slug 与文件映射匹配。无新增缺陷，Pass；上面两份正文 SHA 未改变。

主线程另行提供站内门禁实证（非本评审者重复执行）：默认生产构建成功；文档阅读器定向 **6 passed (15.9s)**，遍历 **72 pages / 74 localLinks，broken=[]**，新例子和指南 HTTP 200。评审者未并行 build，未将主线程实跑表述为独立浏览器实跑。

```text
78f59b50e7fb95519b65441c99b0021eda69802ce996ff2c2359c2b4e8e1cc69  frontend/lib/documentation.ts
de7e9c16af666d6b7e51d2c748a60a23d6e33698e0d5f534d5ca04aa6f324c52  docs/README.md
```

## 9. 迁移说明与阶段进度增量复核

2026-10-14，独立增量复核 `docs/27-local-development-guide.md` 两处迁移说明及 `docs/26-p0-06-candidate-verification.md` 第8节。**Pass，无新增缺陷。** 指南移除会随分支失效的固定迁移版本，链接到实际 `RunStore.REVISION`；停写、SQLite 一致性备份、显式 `runs init`、GET 不自动迁移的步骤仍完整。源码相对链接在 GitHub 可用，站内遵循既有源码仓库链接规则。

P0-06 当前已有部分基础模块，因此上文初评时的“设计阶段”属于历史快照；新进度明确父任务 `in_progress`，未开放候选 CLI/API/网页，待完成清单包含 T05、执行恢复及模型对照。53/102/133 等批次数字对应已落地独立报告，并明确有重复用例、不能求和。全部5条评审链接存在。未将合成账本测试当作模型或容器效果。

本次只读文案与直接引用源码，不重跑 CLI，也不迁移数据库。主线程提供的后续集成证据为151项候选相关门禁（其中19项真实 Docker）、fresh mypy 83源文件通过；它们不是本评审者重新运行的结果，也不代表 P0-06 全闭环交付。

```text
24ae79053dfb184bfdf0c94cb9124953d4bb14709cbc621d064fca0e48edf24b  docs/27-local-development-guide.md
6663381a7863ab64e329f1cce95b00773d9ff3bf8764d5e26afd4600ba4de61c  docs/26-p0-06-candidate-verification.md
```

## 10. 最终基础模块进度与本地整合文案复核

2026-10-14，范围为 docs26 第5节迁移版本、§8 的 T05 行及整合实证，以及 docs03 父任务状态。**Pass，无新增缺陷。** T05 行134项与独立账本评审一致；迁移0004～0006与现有链一致。父 P0-06 在台账及规格首部/§8 均为 `in_progress`，待完成模型反馈、宿主中断后精确回收、候选与回归API/网页、公平模型对照，未将基础模块评审计为完整产品完成。

只读核对本机 `artifacts/p006-integration/migration.json` 与对应脚本：脚本通过 SQLite backup 保存旧库，升级前后规范化比较8个旧表全部行，记录 `0003_analyses → 0006_reproductions`、`unchanged=true`、`integrity_check=ok`，其中5条运行/3条分析，与文档一致。这是主线程实际执行证据的独立阅读，评审者未再次迁移或修改数据库。停写和服务重启依据主线程操作说明，本次未重新进行进程操作。

846 passed /49 skipped 与后续4项独立反例分开列出，未冒充同一次850通过；candidate151项中19项实际Docker、其余确定性检查的口径正确，不包括模型实验。fresh mypy86源文件为主线程提供的整合门禁结果；本次没有重复重测试或build。页面最终构建/定向UI门禁仍由主线程继续，不在此报告中提前宣称通过。

```text
e79a4c4f5dc4f8c83433667400a3af757bedfc87a8ef8fe51730295e2b8d5516  docs/26-p0-06-candidate-verification.md
0a54c75a51246f20797dedb3caa86b61bcb7a8403264c7b07eae6bca7b19340f  docs/03-roadmap.md
```
