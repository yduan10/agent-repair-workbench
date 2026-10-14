# P0-05b 交付与验收记录

日期：2026-10-14。Feature P0；状态 done；planned → ready → in_progress → in_review → done，工程门禁与独立增量复审通过。规格见 [24](24-p0-05b-runtime.md)，验收要求见 [17](17-agent-tools-testing-plan.md)。

## 1. 本批能做什么

- CLI `analyze` 发起 check_only / diagnose / propose_repair；`analyses list/show/reconcile` 查询或对账。
- 诊断、修复建议、验证解释分别有角色实现、严格输出契约和提示词。共享 LangGraph 有限循环、DeepSeek 兼容网关、预算及停止控制器。
- 五类受控工具已实现：读取注册证据、读取工具契约、读取授权源码片段、确定性契约检查、实际 Docker/MCP 复现。
- SQLite 0003 持久化安全摘要、结构化事件和执行关联。预算预留先提交再外发；重复请求不重新授予执行权；终态及用量不可倒退。
- 诊断页读取真实记录，展示三角色判断、调用步骤、证据引用、已知用量/未结算预留、关联运行及安全摘要下载；CLI 入口在页面内。无模型配置时不伪造结果。

**阶段边界**：目前只允许两个已审核的合成案例；网页不发起模型请求。`proposal_only` 是临时源码片段建议；不写源码、不应用补丁、不声明修复成功。验证角色只核对证据和候选元数据。实际候选编辑、冻结回归及审批还未实现。

## 2. 真实模型 A14：全部尝试与结果

使用用户现有兼容网关请求 `deepseek-v4-1-flash`。凭据只在交互调用进程内，不保存到文件、日志、参数或仓库。发送的是审核合成案例和已授权的四行源码片段；不是用户私有项目。

| 尝试 | 结果 | 用量与轮次 | 处理 |
|---|---|---|---|
| 第一次完整任务 | HTTP 400，outcome_unknown | 1 次模型请求；usage 未知，保留 1,052,672 tokens 预留 | 修正工具参数 schema 为根 object 包裹 decision，并保持严格角色解码；未自动重投旧任务 |
| 第二次完整任务 | budget_exceeded | 12 模型 / 10 工具 / 1 建议；输入 87,031、输出 2,317 tokens；23.315 秒 | 验证阶段重复读取证据用完调用次数。修订宿主交接，直接传入已校验的证据摘要；保持 12 次上限 |
| 第三次完整任务 | proposal_only | **7 模型 / 4 工具 / 1 建议；输入 41,644、输出 1,541 tokens；14.131 秒** | 诊断→建议→独立证据核对完成；usage_complete=true、预留余额 0，无错误事件 |

另做过一次小型结构化 HTTP 兼容探针，返回 HTTP 400、用量未知；它不计入上表完整任务，也不算成功验收或零费用调用。

最后一次每轮输出：诊断 146/148/290，修复建议 151/350，验证解释 161/295 tokens，最大 **350**。单轮配置上限分别为 4,096 / 8,192 / 4,096。提高上限不要求模型用满；本例的重复取证与上下文开销比输出截断更突出。没有做 2,048 与新上限的对照实验，不声称复杂任务质量或时延已证明不受影响。

第三次运行只调用读取源码/契约类工具；不能说真实模型这一轮执行了全部五工具。T04/T05 由独立的确定性及真实容器门禁验证。三个完整任务都保留在本地记录中；不能把最后一次成功包装成 100% 成功率或真实项目修复率。

本地证据（忽略入库）：`artifacts/p005b-acceptance/model-first-http400.json`、`model-second-budget-stop.json`、`model-result.json`。最后任务 ID `08cb31b9-9870-41ff-bb1f-c7873bf5108d`，摘要 SHA-256 `87a54c2f9764ed80253fb7a2c70ce48649fc96d88d1353ca7804688589db896e`。

## 3. 预算口径与已知限制

官方模型文档说明与用户授权映射详见 [24 §3](24-p0-05b-runtime.md#3-模型适配与预算)。本批 profile 条件性信任该模型的 1M 上下文声明，每轮预留输入 1,048,576 加角色输出上限；默认任务 2,000,000 是累计已知用量与未结算预留的约束，不是一次请求实际消耗。合法 usage 结算后释放差额。

没有取得网关管理配置，不能宣称验证了上游身份或实际强制上限。没有配置价格，费用始终未知。缺失/超界 usage、超时、取消及截断均停止，未知用量保留预留；不自动补发写操作、不承诺 exactly-once、不恢复重放模型图。

## 4. A01～A15 测试映射

| 验收 | 证据位置 | 判定 |
|---|---|---|
| A01 意图区分 | `tests/agents/test_runtime.py` | check_only 零模型；诊断与建议继续到各自终态 |
| A02 工具反馈 | 同上 + `test_runtime_handoff_review.py` | 后续决策得到实际证据；新角色收到注册摘要 |
| A03 缺证据拒判 | 角色契约测试 + runtime 停止用例 | 不产生已证实根因或 candidate_verified |
| A04 严格模型输出 | `test_gateway.py`、`test_reviewer_gateway.py`、runtime | 错枚举/字段/多调用/重复键拒绝，纠正最多一次，截断不纠正 |
| A05 角色权限 | `tests/test_controlled_runtime.py`、runtime 越权编辑测试 | 修复角色无执行权，T06/T07 未注册 |
| A06 注入 | `test_injected_source_never_grants_secret_access`、`test_dynamic_injection_cannot_grant_paths_or_execute` | 凭据不进入请求，指令不增加权限/预算 |
| A07 引用归属 | resources、store、runtime 测试 | 跨任务/伪造/旧 hash 拒绝 |
| A08 预算账本 | gateway、runtime、analysis_store 及 reviewer store | 先预留后请求；重复结算/非法 usage 拒绝，不出现负额度 |
| A09 超时取消 | reviewer gateway 整请求时限探针；runtime reviewer；真实 T05 | 包含分段滴流、原生重复取消、未知结果保留及清理 |
| A10 有限循环 | runtime / runtime_reviewer | 模型、工具、建议数、总时限阻止下一次执行 |
| A11 文件边界 | `tests/test_controlled_resources.py` | 路径逐级防软链接、特殊文件/过大文件/快照变化拒绝 |
| A12 独立验证 | runtime 与独立 handoff review | 不继承其他角色聊天、成功自述、原始事件、候选正文 |
| A13 幂等执行 | store / controlled_runtime / runtime_reviewer | 事务绑定分析与 run；重复 ID 只读原结果，异参拒绝 |
| A14 真实模型 | 本文 §2 | 一次完整协作完成；保留两次未完成任务及兼容探针 |
| A15 真实前端 | `frontend/tests/analyses-live.spec.ts` | 临时 SQLite：真实 CLI→API→页面→下载→断网恢复；模型调用 0 |

`analyses.spec.ts` 的错误/竞态/主题测试使用边界 HTTP 样本，不能替代 A15 真数据库链路。真实模型表现和确定性工程测试分开报告。

## 5. 执行命令与结果

| 门禁 | 命令 | 本次结果 |
|---|---|---|
| 全部默认 Python 回归 | `uv run pytest -o addopts='--import-mode=importlib' -q` | 554 passed / 30 skipped；跳过不算通过 |
| 既有执行器 Docker | `AWB_DOCKER_TESTS=1 uv run pytest -m docker` | 25 passed / 3 skipped（T05 另设显式开关） |
| 五工具 T05 Docker | `AWB_TOOL_DOCKER=1 uv run pytest tests/test_controlled_tools_docker.py` | 3 passed：正常/输出错类型/原生取消回收 |
| 静态检查 | `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy --no-incremental src`、`uv lock --check` | 全部通过，67 个生产类型文件 |
| 主浏览器回归 | `npm run test:e2e` | 82 passed / 3 显式 live 用例跳过；首轮旧状态断言及隔离 Origin 配置问题已修正复跑 |
| 运行记录独立链路 | `npm run test:runs-live` | 21 passed |
| 分析独立链路 | `npm run test:analyses-live` | 1 passed，包含下载内容核对；独立临时数据库，不触碰用户记录 |
| 前端构建/类型 | `npm run build`、`npm run typecheck` | production build 与 TypeScript 通过 |
| 运行依赖审计 | frozen no-dev requirements + `pip-audit --no-deps --disable-pip` | 61 个运行依赖，0 已知漏洞、0 跳过 |

不把本次未重新执行的公开历史故障、待实现 P0-06 测试或远端 CI 算作通过。CI 新增独立分析链路，不在 CI 注入模型密钥。

## 6. 迁移、页面与独立评审

主数据库停写、一致性备份后显式迁移至 0003；原 runs=4、attempts=4、events=12、artifacts=4、web_requests=2 的逐表原记录哈希一致。未把开发测试临时数据库导入主数据库。迁移预像与备份仅留忽略目录。

| 范围 | 独立报告 |
|---|---|
| 设计 | [设计预审及复审](reviews/P0-05b-design-review.md) |
| 网关 | [网关复审](reviews/P0-05b-gateway-review.md) |
| 持久化 | [存储与对账复审](reviews/P0-05b-store-review.md) |
| 工具 | [工具与取消复审](reviews/P0-05b-tools-review.md) |
| 编排 | [运行及证据交接复审](reviews/P0-05b-runtime-code-review.md) |
| 前端 | [UI/API 与真实链路复审](reviews/P0-05b-ui-review.md) |
| 交付文档 | [独立交付复审](reviews/P0-05b-delivery-review.md) |

已修复的关键问题包括：HTTP 总时限未覆盖完整响应、非法内容导致合法 usage 丢失、重复保存可能再次授予发送权、原生取消留下后台检查/清理任务。独立反例及修复后的快照保存在各报告中。

## 7. 下一项：P0-06

下一步先冻结候选编辑格式及范围、基线与候选独立副本、只读验收输入和可信外部 oracle。通过 R01～R11 后才允许 candidate_verified，并同步候选 diff/回归网页。需要包含“修好当前错误却破坏旧行为”的反例及同模型/工具/预算的单 Agent 对照。

当前没有私有项目接入、自动修复率、三角色优于单角色或用户需求验证结果。P0-05b 的通过只说明有界协作与证据链已运行；产品完整修复闭环仍依赖 P0-06。
