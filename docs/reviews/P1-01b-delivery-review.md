# P1-01b 交付文档与能力状态一致性审计

- **审计对象**：README；docs/27、29、30、03；frontend/lib/capabilities.ts、milestones.ts、documentation.ts，共8文件、约866行。
- **审计版本**：2026-10-14 工作区；冻结摘要见文末。P1-01b 在审阅时为 in_review，P0-06 为 in_progress。
- **技术栈**：Markdown、TypeScript能力目录；实际Python/ASGI/SQLite/Docker证据只用于核对陈述。
- **业务场景 / 严苛度**：General SaaS / Mission-Critical。
- **审计方式**：采用 auditing-enterprise-code-quality skill，按文档和能力目录实际适用范围审查。
- **独立性**：本审阅者没有编写本批产品说明/台账/能力目录。本人曾实现B2服务并编写B4测试，故本报告**不代替B2生产代码独立评审，也不自批B4测试代码**；B2另有服务独立评审，B4由root独立阅读并复跑。

## 1. 代码质量评估卡

- **结论：Pass（交付文档与能力状态一致性）**。允许把本批从 in_review 更新为 done，并保留P0-06未完成状态；状态同步后需重新构建站内文档。
- **得分：100/100**。初查2项Defect P2、1项Defect P3，作者修复后已复核关闭，当前未解决项均为0。
- 本结论不代表商业验证、真实用户修复率、任意工具支持或全仓新一轮测试通过。

| 未闭P0 | 未闭P1 | 未闭P2 | 未闭P3 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |

```text
STRICTNESS: Mission-Critical
SCENARIO: General SaaS
DEDUCTIONS: open findings = 0
RAW SCORE: 100
CAP APPLIED: none
FINAL SCORE: 100 / 100
VERDICT: Pass for delivery documentation/capability consistency
NOT ASSESSED: full production code re-audit; model accuracy; OS SIGTERM/KILL integration; full supply-chain rescan
```

## 2. 生产事故风险推演

无未闭Defect P0/P1。文档不得把收到工具结果后取消说成工具没有执行；当前docs30正确区分已观察响应、未完成检查、分析取消与资源回收。

## 3. 详细审计明细

### Defect P0 / P1

none。

### 已关闭 D-1：首次网页启动缺初始化步骤（Defect P2，confirmed）

- **位置**：初审docs/27-local-development-guide.md:40–43；README网页入口指向该章节。
- **维度**：7运维、10一致性。
- **失效场景**：首次clone仅按网页启动步骤启动API/前端，没有状态库。分析/运行页面的读取不会创建数据库，返回store_not_initialized，用户无法执行页面所示能力。后文单独出现runs init不能替代按顺序启动的前置条件。
- **修复**：作者已在该章节API命令之前加入首次安装runs init，已有库必须停写备份再升级，不引入GET自动迁移。
- **复核**：复读docs27，并核对现有B2 missing-store测试与服务不自动初始化规则。关闭。

### 已关闭 D-2：“完整门禁”漏独立测试开关（Defect P2，confirmed）

- **位置**：初审docs27:121–122。
- **维度**：9可测试性、10一致性。
- **失效场景**：原命令只有AWB_PUBLIC_CASE/AWB_DOCKER_TESTS/AWB_TOOL_DOCKER，新网页分析Docker与P0-06候选测试仍skip，却被称为“完整门禁”。
- **修复**：作者将旧命令限定为P0-02～05，单列AWB_WEB_ANALYSIS_DOCKER=1及P0-06镜像准备/AWB_CANDIDATE_DOCKER_TEST=1，未把未开发完批次计作完整产品验收。
- **复核**：与tests/test_web_analysis_docker.py、tests/test_candidate_docker.py、tests/agents/test_repair_tool_bridge_docker.py实际环境门禁逐项对应。关闭。

### 已关闭 D-3：侧栏状态文案滞后（Defect P3，confirmed）

- **位置**：初审docs27:55；对照frontend/components/sidebar.tsx。
- **修复**：改为仅提示开发中/规划中模块，已可用模块直接进入操作页；与UI-07及当前capabilities一致。关闭。

### 验证证据及边界

1. 文档局部链接脚本：85个相对文件引用、10个文档导航slug，缺失0。未把外部网页可用性计入该检查。
2. 检查历史ID：旧版本所有里程碑仍保留，无重复ID；P1-01b作为新记录，未覆盖P0-05b当时“网页只读”的历史。
3. 实际只读HTTP：8030 `/api/agent-contracts` 为200，`catalog_version=3`，CLI/web能力均true；3010 `/docs/30-web-analysis-delivery`、`/workspace/diagnosis`、`/workspace/connections`均200。未读取主库原始记录或密钥。
4. 页面路由对应真实组件：diagnosis→AnalysisHistory/AnalysisConsole，connections→ConnectionsConsole；repairs/regression/memory仍是明确预览。目录只表示能力，运行就绪来自analysis-runs/catalog，docs27有明确区分。
5. B4本人运行原始输出：`3 passed in 4.81s`；未打开显式门禁时 `3 skipped in 1.32s`。模型为确定性stub，实际ASGI路由、SQLite、MCP与Docker执行。取消和shutdown在真实SDK响应后暂停，先确认精确容器Running，随后回收并验证absent。正常场景diagnosis_complete/契约failed；取消场景cancelled/契约inconclusive。不能当作真实模型效果或操作系统进程信号验收。
6. root独立复跑B4三项通过，已作为docs30来源；此前一轮1pass/2fail是测试错误期待响应已观察后仍outcome_unknown，实际三个容器均回收，修正测试断言且未改生产。全部尝试保留在artifacts/web-analysis-docker/summary.json。
7. 真实模型/浏览器与主库迁移计数由root执行及docs30来源记录提供，本评阅者未重调模型或重迁主库。docs30保留失败尝试，未把最终两项通过覆盖此前失败；主生产浏览器写32/33通过、修正旧入口断言后单项通过，未伪称单次33全部通过。
8. README/能力目录/台账均把proposal_only解释为建议未应用，P0-06完整修复/候选网页/公平对照未完成。无任意仓库支持、自动修复成功率、凭哈希证明归因等超范围陈述。

## 4. 维度覆盖声明

| # | 维度 | 未闭发现 | 本批结论 |
|---|---|---|---|
| 1 | 架构与边界 | 0 | 固定案例、有限角色、程序判定、P0-06未完成边界一致 |
| 2 | SOLID | 不适用 | 本批为文档/展示目录，不重审服务实现 |
| 3 | 并发与资源 | 0 | 文档区分取消请求、实际终态、孤立恢复，不宣称自动续跑 |
| 4 | 容错 | 0 | 失败验收尝试保留，恢复步骤不生成新执行 |
| 5 | 性能 | 不适用 | 未提出新吞吐/规模承诺 |
| 6 | 安全合规 | 0 | 仅环境提供凭据；不在报告读取或输出密钥；案例边界明确 |
| 7 | 可观测/运维 | 0 | D-1关闭；首次启动、迁移、模型重启说明可执行 |
| 8 | 类型/契约 | 0 | 目录版本3，页面入口与真实接口相符 |
| 9 | 测试 | 0 | D-2关闭；fake/真实模型/容器/浏览器计数分开 |
| 10 | 规范一致性 | 0 | D-3关闭；链接、历史、任务状态一致 |
| 11 | 数据完整性 | 0 | 备份与显式迁移写明；不把主库数据当验收夹具 |
| 12 | 依赖治理 | 不适用新增依赖 | 本批文档/能力目录未新增依赖；未重做全仓扫描 |

## 5. 整改清单

| ID | 严重级 | 负责人 | 截止 | 状态 |
|---|---|---|---|---|
| D-1 | P2 | root | P1-01b done之前 | 已修复复核 |
| D-2 | P2 | root | P1-01b done之前 | 已修复复核 |
| D-3 | P3 | root | 本次文档更新 | 已修复复核 |

剩余为交付动作：root同步docs03/29/30与milestones为done、补本报告链接、重建站内文档。以上仅状态及证据引用更新不新增能力承诺；若增加实质陈述须复核。

## 6. 架构防腐与长效治理建议

1. 每新增独立验收环境开关，同步运行指南；保持skip不算通过，成本是更新一行命令和对应测试来源。
2. 后续批次保持能力目录、路由、里程碑和README同步；保留历史当时边界，不能全局替换“只读”毁掉旧交付记录。
3. 容器测试保留精确身份、执行结果与清理断言；模型效果报告独立记录，防止把stub覆盖当实际模型质量。

## 7. 审计声明

本报告仅评审交付文档及能力一致性，未修改任何生产逻辑。无风险豁免。已通过的独立服务/控制台/证据审查各自保持原范围，当前报告不扩展它们。冻结文件摘要如下；状态及本报告引用的纯交付更新可按上文执行，其余修改须按影响复审。

```json
{
  "README.md": "017d04c77d60cb777dfbebaaba164a940c5cd54098f7453f97a83a0ffbb88834",
  "docs/27-local-development-guide.md": "94c478b40c7a0c8edbe069ea03eddec62d16faf3973adb8b76763eb9e39561af",
  "docs/29-web-analysis-console.md": "7f2153ab8d784001121aa9052195d342c214e99c754d73a3bee0af3e16b30caf",
  "docs/30-web-analysis-delivery.md": "cb63028c2a5a94b843ec669f536f6908380d21bea9f0f87e1078358f86963ad9",
  "docs/03-roadmap.md": "976c8c36fcb0bf3e4fa11c7d7340cb224cbe579a2c797b80849017fd973658a6",
  "frontend/lib/capabilities.ts": "8e133c1a6f3333ff363aa4a1f94f818c04404d607690b5fdd2ab87123d63cd45",
  "frontend/lib/milestones.ts": "586d47c1754c9dcb3edf68f8807031818a56f35cff1c472e239b100b37956bbe",
  "frontend/lib/documentation.ts": "0e5081bfb03734e140393242667bf3ea40e17ecb7e443a6ed8c06aa2e4d54e19"
}
```
