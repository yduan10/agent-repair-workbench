# P0-05a 实现与验收记录

2026-10-13 / P0-05 第一批。设计冻结于 [18](18-p0-05a-contracts.md)，独立预审见 [设计评审](reviews/P0-05a-design-review.md)。本记录单独追加，不改写预审快照。

## 1. 实际交付

- `agents/diagnosis|repair|verification/contracts.py`：三角色严格输出、候选建议边界、独立角色测试；没有伪造agent.py或模型循环。
- `controlled_tools/contracts.py`：五类工具请求、路径和行数限制、统一精确授权key；没有执行handler。
- `orchestration/contracts.py`：TaskSpec、Budget、TaskState、Usage、AnalysisSummary；安全摘要无原始模型/源码字段。
- `orchestration/codec.py`：64KiB/深度20、重复键/非有限数/非法格式拒绝，固定错误不回显原文。
- `orchestration/policy.py`：任务/证据/精确资源/编辑范围校验，意图匹配、状态边、CAS版本与终态保护。此处是纯程序校验，不宣称已持久化任务或执行工具。
- `GET /api/agent-contracts`：真实只读catalog，生成可下载JSON schema；不读模型配置、不创建数据库、不提供invoke端点。
- 前端工具接入与诊断页新增“协作接口”，角色tab、权限列表、折叠schema、JSON下载、失败重试；诊断状态更新为开发中。DOC-03与P0-05a追加历史，旧记录全部保留。

预算本批只实现配置与摘要一致性，预留/结算运行算法、模型适配与工具副作用去重属于P0-05b。模型输出不含角色/任务/最终通过授权；这些由宿主决定。查询实际证据文件、模型外发审批、候选应用均未开放。

## 2. UI设计与实际检查

使用frontend-design skill，沿用产品主题：画布#eef3fa、表面#ffffff、正文#16243d、次要文字#52627b、强调#335cde、分隔#dfe6f0；深色由已有主题变量映射。字体沿用产品字体层级，不引入新字体依赖。

布局为单一目录区域：标题/能力边界→三个角色tab→按行展开工具→输出格式与下载。tab下划线160ms过渡表达当前选择，reduced-motion关闭过渡；工具字段使用有限高度滚动区域，避免JSON撑宽页面。现有CLI入口和下方预览流程保留，真实目录位于预览说明之前。

实际IAB检查截图：`artifacts/p005a-ui.png`；自动化四种视口/主题截图：`artifacts/p005a-{light,dark}-{1280,390}.png`。

## 3. 验收证据

| 项目 | 命令/证据 | 结果 |
|---|---|---|
| 新契约与既有API | `uv run --frozen pytest tests/agents tests/tools src/agent_workbench/agents tests/test_api.py` | 86 passed，含9个独立反例 |
| 非容器/非公开来源准备门禁 | `uv run --frozen pytest -m 'not docker and not public_case'` | 395 passed，22 deselected，35.62s；本次执行器无改动，未重跑这22项 |
| 测试发现 | pytest `testpaths`加入三角色tests；collect-only | 最终417项可发现；早期408项后加入9个独立反例 |
| 静态与版本 | Ruff check/format、mypy --no-incremental、uv lock --check | 已通过，mypy40生产源码；角色测试与既有根tests相同不纳入生产mypy |
| 网页 | TypeScript、production build | 已通过 |
| 定向浏览器 | agent-contracts全部6项 + progress/appearance相关2项 | 8 passed，9.4s，真实API下载内容一致，四组合axe无违规 |
| 独立后端review | [后端评审](reviews/P0-05a-code-review.md)及SHA清单 | 3个P2修复复审关闭 |
| 独立前端review | [前端评审](reviews/P0-05a-ui-review.md)及SHA清单 | 6项新UI+5项独立故障探针通过，无未闭缺陷 |

C01～C07与测试映射：C01→`tests/tools/test_contracts.py`、`test_strict_boundaries.py`；C02→角色tests与`test_policy.py`；C03→tools/policy反例；C04→policy意图/CAS/终态；C05→`test_summary_api.py`；C06→同文件真实API/meta-schema；C07→`frontend/tests/agent-contracts.spec.ts`。

初审修复：CAS比较拒绝bool/float；相对路径补拒C1控制字符；JSON指数溢出拒绝inf。独立9个反例在旧实现全部失败，在最终实现通过；删除不必要typeignore并以无缓存mypy验收。新代码没有引入依赖，uv.lock未改动。

## 4. 用户模型接口兼容性探针（单独记录）

用户本轮提供既有网关并要求查询模型；凭据通过隐藏输入仅在测试进程内使用，未写入项目、UI、报告或环境配置文件。

- GET `/v1/models` 返回200、27项模型标识。DeepSeek包括 `deepseek-v4-1-flash`、`deepseek-v4-flash`、`deepseek-v4-pro`；其余有GPT、Claude、GLM、Kimi和图像模型条目。列表不代表每项已实际调用，网关标识不证明背后模型部署身份。
- 对 `deepseek-v4-1-flash` 作一次合成 `emit_probe(status=ok)` 工具调用：HTTP200，恰好一个工具调用，名称与JSON参数校验通过；返回模型标识 `deepseek-v4-1-flash-260910`。
- 实测1.14s，接口报告prompt318、completion55、total373 tokens（含reasoning17）。未取得可靠价格，因此不报告金额。
- 该探针只证明一次Chat Completions/tools接口兼容；不是P0-05b模型网关、完整A14或Agent效果评测通过，不据此开放用户数据外发。

## 5. 接续工作

P0-05父任务保持in_progress。下一批P0-05b按18规格先冻结工具响应、真实证据注册和模型调用的预算保留/结算，再接入已验证的DeepSeek模型。新增analysis存储/Alembic迁移及只读结果API仍需增量设计评审。运行循环和A矩阵全部验收后才能把P0-05整体标done；P0-06再处理真实候选副本与独立黑盒验收。
