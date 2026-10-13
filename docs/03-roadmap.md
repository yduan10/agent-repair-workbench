# 优先级、迭代与验收台账

版本 0.1 / 2026-10-13。此文件是完成进度的唯一来源。

## 1. 优先级定义

- **Feature P0**：建立“真实失败→局部修复→独立回归”闭环不可缺少的工作；按依赖分期，不表示今天全部开发。
- **Feature P1**：闭环通过后，让开发者持续使用、验证适配性的工作。
- **Feature P2**：真实使用证据支持后再排期的扩展。
- **Defect P0/P1/P2/P3**：代码缺陷严重程度，见质量门禁；与功能优先级无映射关系。

状态：planned / ready / in_progress / in_review / done / blocked。done 必须附测试和评审证据。预计工作量为单人专注开发的粗估，不是截止日期；复杂度超预期必须拆分，不削减验收。

## 2. P0 台账

| ID | 迭代 / 工作项 | 依赖 | 估计 | 状态 | 完成证据 |
|---|---|---|---|---|---|
| DOC-01 | 范围、约束、架构、台账、质量和首项规格 | 无 | 本次 | done | [DOC-01 评审](reviews/DOC-01.md) |
| P0-01 | M0 契约检查器、CLI、结构化证据报告 | DOC-01 | 1–2 天 | done | 86 tests、Ruff、mypy、锁检查通过；[独立代码评审及复审](reviews/P0-01-code-review.md) |
| UI-01 | 产品首页、完整模块预览与真实检查 API | P0-01 | 本次 | done | 99 Python / 9 E2E；[代码评审](reviews/UI-01-code-review.md)、[文档复审](reviews/UI-01-P0-02-design-review.md) |
| UI-02 | 三态主题、交互动效、完整历史与功能进度同步 | UI-01 | 本次 | done | 18 E2E、浅深色 36 组合、短桌面导航复审；[独立 UI 评审](reviews/UI-02-independent-review.md) |
| DOC-02 | 产品 Agent 分目录及维护指南 | DOC-01 | 本次 | done | [维护规范](09-agent-modules.md)；[独立评审](reviews/P0-02-independent-review.md)，不计 Agent 运行实现完成 |
| P0-02 | M1 MCP stdio 真实调用与协议适配 | P0-01 | 2–3 天 | done | 156 Python tests（含独立环境公开案例）；[独立代码复审](reviews/P0-02-independent-review.md) |
| P0-03 | M1 受控执行、故障注入、取消与进程回收 | P0-02 | 3–5 天 | done | 284 Python（含18真实Docker）/18 E2E；[验收证据](11-controlled-execution.md)、[Docker独立评审](reviews/p0-03-docker-review.md)、[UI复审](reviews/P0-03-ui-review.md)；状态按planned → ready → in_progress → in_review → done流转 |
| UI-03 | 模块状态与首屏能力进度同步 | P0-03 | 本次 | done | [完成记录](13-ui-progress.md)、[独立评审](reviews/UI-03-review.md)；19 E2E/build/typecheck通过；planned → ready → in_progress → in_review → done |
| P0-04 | M1 运行状态、产物、恢复对账 | P0-03 | 2–4 天 | done | [后端验收](14-run-store.md)、[真实记录页](15-run-history-ui.md)、[store评审](reviews/P0-04-store-review.md)、[协调评审](reviews/P0-04-coordinator-review.md)、[UI评审](reviews/P0-04-ui-review.md)；340完整Python+4独立反例，29主UI+20隔离UI通过；planned → ready → in_progress → in_review → done |
| UI-04 | 产品信息入口与工作导航分层 | P0-04 | 本次 | done | [设计及验收](16-navigation-hierarchy.md)、[独立复审](reviews/UI-04-review.md)；build/typecheck及8项修复后定向验收通过；planned → ready → in_progress → in_review → done |
| DOC-03 | 产品闭环、Agent/tools边界与测试用例规格 | P0-04 | 本次 | done | [实施规格](17-agent-tools-testing-plan.md)、[独立文档复审](reviews/DOC-03-review.md)；8工具/26验收用例矩阵及链接核对，D01/D02修复复审；planned → ready → in_progress → in_review → done；不计Agent运行实现完成 |
| UI-06 | 站内工程文档阅读器与排版 | UI-05 | 本次 | done | [规格](21-ui-06-document-reader.md)；planned → ready → in_progress → in_review → done；[复审](reviews/UI-06-code-review.md) |
| UI-05 | 功能引导、文档入口、主题修复与公开源码 | P0-05a | 本次 | done | [范围与验收](20-ui-05-public-source.md)；planned → ready → in_progress → in_review → done |
| P0-05 | M2 三角色有限循环、模型适配与预算 | P0-04 | 3–5 天 | in_progress | planned → ready → in_progress；[P0-05a已完成](19-p0-05a-delivery.md)，独立前后端复审通过；P0-05b及完整A矩阵待实现，完整里程碑未完成 |
| P0-06 | M2 隔离补丁、冻结验收、基线候选比较 | P0-05 | 3–5 天 | planned | 待实现 |

负责人：实现 Codex，产品验收 Yukun，质量门禁由专职 reviewer 出具证据。所有 Defect P0/P1 必须在对应任务标 done 前修复；不能用上述估计作为豁免。

### P0-01 验收

- 输入/结果 schema 校验、工具名与调用 ID 关联、错误状态、缺失结果等按 05 规格输出。
- 有效调用通过；schema 无法支持或检查器无法完成时 inconclusive，绝不伪装通过。
- 显式记录检查范围：输入检查可通过，但缺 output schema 的输出检查为 not_checked。
- JSON Pointer 与错误代码定位；不输出原始参数值、结果值、异常消息。
- 输入限制、严格 JSON、schema 限制、CLI 限时与退出码有负向测试；报告含版本和规范化证据哈希。
- 至少提供合成成功、合成失败两个样本，清楚标注来源。pytest、静态检查、独立 code review 通过。

### P0-02 验收

- 固定版本官方 SDK 连接受控本地 stdio server，实际执行 list_tools/call_tool 并保存版本化证据；不使用 mock 代替唯一集成验证。
- 适配 missing output schema、isError、非结构化内容、关联 ID，拒绝未经规范支持的数据转换。
- 至少复现一个有来源和固定版本的公开问题；若无法复现，记录失败原因并保持此门禁未完成。
- 外部工具启动需显式配置，不将输入中的 shell 指令直接执行；参数使用 argv。

### P0-03 验收

- 固定 seed 注入超时、工具错误、响应丢失、重复结果；区分传输错误与工具失败。
- 子进程树取消/超时回收，限制 CPU/内存/输出；写副作用超时进入 outcome_unknown。
- 测试进程在执行前/执行中/结果返回前被杀；不得挂死或误报成功。

### P0-04 验收

- 原子状态事件、乐观并发、唯一 run/attempt ID；两个 worker 竞争不能双占有同一执行。
- 重启对账、过期 lease、重复事件、数据库 busy 和磁盘写失败有测试。
- schema migration 升/降级演练；本地产物摘要可校验；清理不删除正在使用的产物。
- 固定本地保留默认 30 天，可配置；提供 dry-run 删除和实际删除命令，原始凭据永不存储。

### P0-05 验收

详细开发批次、工具 T01～T05、必测 A01～A15 见 [17](17-agent-tools-testing-plan.md)。P0-05a 先评审角色/tool schema、摘要存储与只读 API，再开始运行实现；本文补充规格不代表 P0-05 已完成。

- 现有 DeepSeek 接口完成一次真实受控调用，密钥不入库；支持用 fake adapter 跑确定性 CI。
- 角色输入/输出和权限有 schema；本阶段仅 fake 或只读协作，模型可建议补丁但不能应用或执行生成代码。真实候选编辑须待 P0-06 的隔离、白名单和固定验收前置检查通过。
- 最多 2 次候选建议，任务默认 10 分钟，token 预算由配置明确提供。
- 调用前预留 max_output_tokens，超预算不得继续调模型；计费未知须显示未知。
- 假设无法复现返回 inconclusive；注入文本不能修改权限、验收或预算。

### P0-06 验收

候选工具 T06/T07、必测 R01～R11 和对照方案见 [17](17-agent-tools-testing-plan.md)。

- 基线/候选独立副本；固定验收文件前后哈希一致；文件白名单之外修改即拒绝。
- 原始失败变通过、固定回归无新增失败才标 candidate_verified；人工接受另记状态。
- 有“补丁通过新用例却破坏旧行为”的失败候选测试；保留它的证据。
- 同任务、模型、工具、预算的单 Agent 对照和成本统计；不能只展示最好一次。

## 3. P1 / P2

| ID | 优先级 | 工作 | 依赖 | 验收 | 状态 |
|---|---|---|---|---|---|
| P1-01 | P1 | Web 运行/审批的真实功能接入 | P0-06 | 输入→运行→证据→diff→回归；断线重连不重复任务；键盘/空态/错误态可用 | planned |
| P1-02 | P1 | 项目经验记忆 | P0-06 | 人工确认、来源、版本匹配、过期/删除；错误经验负向测试 | planned |
| P1-03 | P1 | CLI/CI 打包与接入指南 | P0-06 | 三个不同工具项目接入，其中一个非开发 fixture；安装/卸载/升级验证 | planned |
| P1-04 | P1 | 使用验证与独立评测集 | P0-03 | ≥10 个来源明确的故障案例；真实/合成分报；记录真实开发者试用反馈或明确未取得 | planned |
| P2-01 | P2 | Streamable HTTP MCP | P1-03 | 认证、重连、版本、SSRF/网络边界方案与集成测试 | planned |
| P2-02 | P2 | 多用户服务、Postgres、任务队列 | 用户需求证据 | 先 ADR 与容量/租户安全验收，再开发 | planned |
| P2-03 | P2 | 新角色/A2A/向量检索 | 实测瓶颈 | 对照证明收益并覆盖兼容与失败语义 | planned |

## 4. 迭代规则

2026-10-13 用户调整顺序：先交付 UI-01，再完成 P0-02 的详细设计和测试矩阵。DOC-01、P0-01 已完成；完整产品 UI 在 UI-01 先行；P1-01 真实运行/审批能力按原依赖排期。每项代码评审后将范围、命令、结果、风险、报告路径补入台账。后一项开始前核对前置门禁；模型凭据等缺失只阻塞依赖它的项，不伪造集成结果。

功能完成度以任务及验收条目描述，不按写了几个模块计算百分比。不把 M0 成功称为 M2 完成；独立评审不等于市场验证。

## 5. 2026-10-13 迭代记录

- DOC-01：初审发现执行隔离前置、M3 接入时机及状态语义问题，已修改并独立复审通过。
- P0-01：完成离线 envelope 校验、schema 子集、输入/结果关联、错误/缺失结果处理、JSON 证据报告、限时 CLI、合成样本及 CI 配置。
- 代码评审 CR-01 发现数值精度误判，已修复并独立复审；报告记录原反例、修复位置及最终哈希。
- 实际验证：`uv run --frozen pytest` 86 passed；Ruff check/format、mypy、`uv lock --check` 通过；两个 CLI 样本分别退出 0/1；23 个已扫描依赖无已知漏洞。
- P0-01 完成时的边界：当时尚未运行真实 MCP、模型修复、Web、远端 CI 或公开安装验证。P0-01 是后续验收基础，不是完整 Agent 产品。
- 后续用户调整：先交付 UI-01 完整产品界面，再按 [08](08-mcp-integration.md) 开始 P0-02；SDK 兼容实验与公开案例仍需实际执行。


### UI-01 完成记录

- 首版产品首页、七个工作区入口（六个明确标注的交互预览）、本地真实检查API、导入编辑与报告下载完成。
- 顺序记录：UI-01 由 in_progress → in_review → done；代码审查发现的取消执行槽、BOM保真、草稿导航、手机溢出、文字对比度、非法路由问题均修复并独立复审。
- 验证：99 Python tests、9 Playwright E2E、16个页面/视口组合axe零违规及无整页溢出；Ruff、mypy、TS、production build、uv lock通过；pip-audit/npm audit当前0已知漏洞。
- 本地网页3010/API8030运行；没有推送、运行远端CI或公网部署。Agent诊断/修复、MCP真实接入和项目记忆存储仍未实现。
- P0-02详细设计与测试计划独立复审通过，状态 planned → ready；下一动作是官方SDK固定版本兼容实验，不能把设计通过计为实现完成。


### P0-02 / DOC-02 完成记录

- P0-02：ready → in_progress → in_review → done。官方 SDK 2.3.0 固定、真实 stdio 握手/分页/预检/单次调用、规范化证据报告与 CLI 完成。仅允许两项经审核 profile，不接受任意 executable/argv/env。
- 固定 python-sdk #3644 提交真实复现：声明 required user_id，实际 serialization alias 不一致，由产品 CLI 确认 output_schema_violation，预期退出 1。1717 个源码文件完整核验并记录源码树摘要。
- 独立审查发现的额外源码文件注入 P1、预检期间取消状态 P2 均已修复复审。审查者新增真实 CLI 污染反例均拒绝，未开始握手。
- 验证覆盖 99 项既有回归、41 项 MCP、15 项来源完整性及 1 项显式公共案例；Ruff / mypy / 锁检查通过；主环境与独立实验依赖均为 0 已知公告漏洞。
- 仍未完成：任意外部代码的容器隔离、进程树/CPU/内存硬限制、状态恢复、模型修复；网页接入仍为预览。SDK 规范化证据不宣称原始 wire 保真。
- DOC-02：in_progress → in_review → done。按用户要求建立 diagnosis / repair / verification 独立职责目录，补新增角色与测试发现维护指南，独立评审通过。未创建空壳 Agent 实现，不提前计入 P0-05。
- 旧 Steam 自启动项已停用，旧目录及归档由用户删除；当前产品只在 agent-workbench 开发，不重建旧目录。


### UI-02 完成记录

- in_progress → in_review → done。新增浅色/深色/跟随系统主题，跨刷新保留偏好、响应系统变化、受限存储降级、键盘操作及 reduced-motion。
- 调整云蓝/深海蓝主题、标题与证据面板入场、用户操作和历史展开动效；未添加装饰波浪。前端同步 MCP CLI 实际完成状态，网页连接仍清楚标为预览。
- 新增完整开发里程碑历史：UI-02、DOC-02、P0-02、UI-01、P0-01、DOC-01。按实际台账补录，不虚构已发布版本。
- 主目录真实 API 的原 9 项 E2E 与新增 8 项外观 E2E 已通过；新增短桌面回归及独立复审通过。36 个浅深色/视口/路由组合 axe 零违规且无横向溢出。
- 独立审查发现的 1280×720 侧栏历史入口不可达 P2 已通过桌面侧栏滚动修复，真实点击、浅深色键盘导航复审通过。最终整合命令与结果见 UI-02 评审/设计记录。

- UI-02 最终主目录整合：production build / TypeScript 通过；完整18项E2E通过（23.6秒），含新增短桌面点击与真实API流程。[最终整合记录](reviews/UI-02-integration.md)。


### P0-04 完成记录

- 运行状态与报告存入本地 SQLite（SQLAlchemy + Alembic）；claim 先提交，再执行工具；终态/事件/报告同事务。
- CAS 与 lease 阻止重复领取和晚到写入。宿主 SIGKILL 后显式对账为结果未知，保持原 attempt，不自动重投；默认30天保留，清理先dry-run且排除未确认资源与无可靠报告的中断记录。
- 任务总览解锁为“记录可用”，显示CLI真实运行列表、状态事件、摘要和报告下载；不把开发测试数量作为用户任务，不自动灌入合成任务记录。当前项目fixture场景的来源有明确标注。
- 340项完整Python回归零skip（21真实Docker、1公开历史案例），再纳入4项reviewer独立反例并通过；Ruff/format/mypy/lock和依赖公告检查通过。
- 主3010前端最终29项通过；唯一临时数据库专用用例在独立8031/3011套件执行，该套件20项通过，独立reviewer复跑通过并补下载取消负例。构建与类型检查通过。
- 实际CLI执行正常调用/响应丢失，经生产本地API→真实页面→下载文件核对SHA一致。只读网页接通；网页发起/取消/审批仍属于P1-01。
- 分批专职review通过，无未闭Defect P0/P1/P2；设计预审D01/D02已补齐并复审关闭。报告与源码SHA清单在reviews目录。
- 下一项按依赖为P0-05：三角色受限协作、已有DeepSeek兼容接口、预算及结构化角色契约。P0-04不宣称模型诊断或自动修复已经实现。

### DOC-03 完成记录

- 按用户要求统一产品闭环、三角色职责、工具输入输出/权限/副作用、自研与第三方边界、模型外发及项目记忆规则。
- 明确 T01～T08、A01～A15、R01～R11；测试是后续验收规格，不作为已通过用例。程序控制器不是第四个模型，P0-05不执行生成补丁。
- 独立文档初审发现任务意图提前截断、候选进程可伪造测试成功两项设计P1；通过任务分支与独立黑盒验收修复复审。
- 同步架构旧状态、SQLite报告BLOB、显式对账及已实现runner/run_store目录说明；七文档链接与矩阵核对，无运行代码/产品能力变更。
- 下一步 P0-05a 冻结角色/tool schema、前台协调与Agent摘要存储/API，之后接入T01～T05和现有DeepSeek；P0-05/06状态仍为planned。

### P0-05a 批次完成记录

- 批次 planned → ready → in_progress → in_review → done；父任务P0-05保持in_progress，不单独累计一份里程碑完成度。
- 独立设计预审后实现三角色严格契约、五类受控工具请求契约（尚无handler）、宿主权限/状态纯策略和AnalysisSummary类型；存储/API写入及模型循环仍属b。
- 实际GET /api/agent-contracts与前端目录接通；工具接入/诊断页可切换角色、查看schema、下载JSON；模型执行明确未接通，迭代历史同步。
- 395项非容器/非公开准备回归通过，22项原执行器门禁本次未重跑；86项后端定向含9个独立反例，前端8项主验收及5项独立故障探针通过；Ruff/format、无缓存mypy40生产文件、锁检查、TypeScript/build通过。最终417项可发现。
- 3个后端P2修复复审；独立[设计](reviews/P0-05a-design-review.md)、[后端](reviews/P0-05a-code-review.md)、[前端](reviews/P0-05a-ui-review.md)报告冻结。详见[实际验收记录](19-p0-05a-delivery.md)。
- 用户现有网关列出27模型；DeepSeek flash一次合成工具调用兼容验证成功，仅算接口探针，非Agent验收完成；密钥未保存。下一批实现P0-05b网关/真实工具/有界协作和安全结果持久化。
