# P0-05b：模型、受控工具与有界协作运行

2026-10-14。Feature P0。状态 done。遵循 01/17/18；父任务 P0-05 已完成本阶段验收，具体结果与边界见 [交付记录](25-p0-05b-delivery.md)。

## 1. 本批交付与入口

- 前台 CLI `analyze` 发起已审核的合成案例，意图 check_only / diagnose / propose_repair；网页只读分析列表、步骤、证据与预算。网页执行与审批仍不在本批开放。
- 三角色分别在 agents/diagnosis、repair、verification 实现 agent.py 与版本化 prompts；共享模型网关、工具、存储。LangGraph StateGraph 执行串行条件边和工具反馈循环；不开启 tracing、自动 retry、持久 checkpoint 重放。
- 先固定一个来源完整的合成输出契约错误，和一个正常案例；为保证T05确实复现同一故障，审核新增Docker fixture固定wrong_type场景（仍限相同资源/断网策略，网页仍仅四场景），重建并验证固定镜像；公开历史案例继续原 CLI 路径，不把合成案例包装为真实用户故障。角色可读取宿主审核的 source snapshot；所有建议只在内存，绝不写源码。
- 五工具 T01～T05 实际执行，T06/07/08 不注册。诊断结论仍 hypothesis/inconclusive；proposal_only 表示未执行建议；不能产生 candidate_verified。

## 2. 公共契约与边界

沿用 TaskSpec / AuthorizationContext / AnalysisSummary v1。所有持久/网络输入重新用严格 schema 校验，不信 model_construct/copy。模型每轮只返回一个 emit_decision 函数的结构化参数，按宿主角色解码；重复键、混合多调用、未知函数/字段拒绝。最多一次结构纠正，网络错误不重试。

模型输出/源码/替换内容只留内存。持久步骤包含固定 kind、role、tool、reason_code、证据引用、调用 ID、请求摘要及数字用量，禁止自由文本。单事件≤16KiB，每任务≤256事件；图状态仅含安全路由状态，不放消息/源码/密钥，显式关闭第三方tracing，不向API/CLI输出graph stream。费用始终 null，未知用量不能显示为零。

工具响应统一含 schema_version、request_id、tool、status（ok/rejected/failed/outcome_unknown）、error_code、evidence_refs、observed_versions、truncated、有界 JSON payload（≤64KiB）。源码结果单次≤200行/16KiB；读取先限整文件≤128KiB，再按行截取；拒绝超限而不静默漏错。源码只从固定注册白名单，逐级 dir_fd + O_NOFOLLOW + O_NONBLOCK 打开常规文件，并核对完整 SHA。模型不提供宿主目录。

## 3. 模型适配与预算

仅接用户现有 DeepSeek 兼容网关，不另选模型或下载模型。配置通过 AWB_MODEL_BASE_URL、AWB_MODEL_NAME、AWB_MODEL_API_KEY 环境提供，凭据不进入参数、日志、摘要或配置 hash；网络不跟随重定向，不继承任意代理，不输出错误响应原文。每次响应有字节、请求时限与结构限制。

**输入 token 上界不得用字符数猜测。** adapter 只有具备可信服务端输入/总上下文硬上限依据时才允许发送：按部署确认的整个输入上限 I + max_output_tokens O 预留；总上下文上限 C 已含输出则直接预留 C。上界证据必须绑定网关模型与计数语义，并记录方法版本。缺少可信上界时返回 INPUT_BOUND_UNVERIFIED，不发送真实请求；fake adapter 提供确定的计数用于工程测试。字节上限只防内存过大，不冒充 tokenizer。

用户随后明确授权依据联网查询的模型上限自行配置。2026-10-14核验官方[模型说明](https://api-docs.deepseek.com/quick_start/pricing/)声明DeepSeek-V4.1-Flash为1M上下文；固定本次用户网关profile采用条件性provider上界信任：输入预留1,048,576（向上覆盖1M），输出按角色限制：诊断/验证4,096，修复建议8,192。请求体≤64KiB，不填充上下文。为容纳预留，将Budget.total_tokens及相关TokenCount（revision Count保持原上限）的最大值兼容扩至2,000,000，默认总额2,000,000；旧≤1M配置仍合法，但额度不足时真实adapter拒发。每次合法usage结算后释放差额，不代表消耗了预留额度；网关标识只表明配置映射，不宣称已独立验证其上游身份或实际强制上限。任意未知模型不复用该profile。

每次模型调用前：本次上限 + 既有已知用量 + 未结算预留 ≤ total_tokens，并校验调用次数/总时限；把 model_calls+1、预留、call_id、阶段与summary版本同事务保存，然后才 HTTP。返回合法 usage 后结算一次；prompt/completion/total 必须非负严格整数且分别不超过预留及请求输出上限，reasoning 若包含 completion 不重复相加。缺 usage、超上界、超时、取消或不确定响应：保留整笔预留、usage_complete=false，停止后续模型调用，不编造实际费用。已观察到的超上界数字仅以固定异常事件表明，不强塞进受预算约束的 known 字段。

预算是应用执行约束，依赖所审核网关执行其声明上限；不宣称可控制恶意第三方账单。只有一次小请求的 usage 探针不能证明输入上界。A14 的兼容调用和上界前置条件分别记录。

## 4. 持久分析、锁与迁移

0002 已用于 Web 请求，本批改用 **0003_analyses**，不改写18历史冻结版本。复用现有 SQLite / SQLAlchemy / Alembic 与 mode=rw，只在显式 runs init 升级。

- analysis_summaries：task_id PK、revision、canonical summary bytes≤256KiB、sha256、updated_at。
- analysis_events：task_id、revision 唯一；每次摘要保存附固定枚举事件及必要安全元数据，禁止模型自由文本。
- analysis_execution_links：record_id 唯一、task_id、request_id、payload_sha256；同(task_id,request_id)唯一。运行记录有链接则 prune 排除。
- 初次 revision0；更新只允许 old+1，与 expected_revision/hash CAS；同版本同hash为幂等，异hash冲突，终态不可新写。固定 intent/source/budget/started_at，计数与已知usage单调，状态按已审 transition。
- 每个 task 的本机 flock 从创建前持有到最终保存/工具清理。显式 analyses reconcile 必须先取得同锁；活着或暂停 owner 拒绝，死后只把未终态标 outcome_unknown，保留原预留和执行链接，不续图、不重发。
- 预算在摘要中先持久化再外发；summary revision 同时充当单轮发送账本序号，call_id 为宿主 UUID，事件记录发起/结算/未知。发起事件保存返回显式 reused；幂等命中绝不再次授予HTTP发送许可。同summary版本/hash但event/call_id不同必须冲突。结算必须引用本任务唯一且未结算的call_id及原I/O预留/方法摘要；重复结算不得二次释放额度。事件字段使用严格DTO，含固定角色判定与reason_code及授权refs，前端可解释结论，不存自由文本或replacement。单前台 owner，无持久队列；重启不重发，因此不必另建可重放消息队列。
- T05 在同一 BEGIN IMMEDIATE 内保存请求去重、创建 run、claim、绑定 analysis、更新 summary，再开始 runner。重复 ID 同参数只返回旧 record（运行中/报告缺失为 unknown），异参数拒绝；崩溃不重复执行。不能先 execute_saved 再绑定，不复用 Web 请求身份/执行槽。

## 5. 资源与证据注册

宿主从审核案例生成不可变任务资源包：基础安全 Report、工具契约快照、源码白名单(path/hash)、固定 case/config、允许请求 target_key。包属于单 task，模型无法添加授权。

T01读取真实注册的安全证据，T02读取匹配revision契约，T03安全打开审核源码，T04复用 checker，T05实际受控 Docker。每个结果核验引用/归属/摘要；同 task 的动态证据由宿主注册，形成版本化 effective TaskSpec.evidence 与 grants，原始任务配置不被模型改写。最多32引用，满则停止。文件或契约快照版本变化拒绝。T05返回的 execution_record_id 绑定由数据库验证，模型不能引用他人的合法 UUID。

安全证据 payload 可从已持久化的 checker/run 报告重建；所有网络回包只保留审查后的固定字段。角色输出引用必须确实来自该任务允许集合。

## 6. 编排规则

queued→checking：先执行确定性检查。check_only 到 check_complete且模型调用0；diagnose / propose_repair 继续所需分析。

诊断可请求 T01～05 并根据工具返回调整下一步；conclude 由程序确认引用存在。diagnose 进入独立 verification 后结束；propose_repair 进入 repair，仅允许T01～03与白名单编辑建议，然后 verification。验证上下文重新组装，只含原任务、工具证据和候选元数据，不继承其他角色对成功的自述、隐藏推理或完整聊天历史。

needs_evidence 不得当完成；有预算时仅 propose_repair 可以再次提案，至多2份。无证据/无法提案/越权/工具未知结果→明确停止。最终 outcome 由程序设置，角色不能赋值。总时限含清理/保存：协调限时提前预留已有 runner 的清理窗口，停止后在有界屏蔽区清理并保存；保存失败保持上一次持久状态，不假报成功。

## 7. 只读 API 与网页

GET /api/analyses?limit=1..50 → {analyses:[{summary,sha256}]}；GET /api/analyses/{uuid} → {summary,sha256,events}。每次读取校验原字节SHA/schema/关系，查询无库list为空/detail404，不兼容或损坏503。复用精确 Host/Origin/no-store，不读模型凭据，不提供 POST。

诊断页提供 CLI 入口、真实分析列表与阶段、固定原因解释、模型/工具调用次数、已知token/预留/未知费用、受控执行证据链接与安全摘要下载。空态说明如何发起，无模型配置时不伪造结果。proposal_only明确“仅建议，未应用、未验证”。先保留当前角色目录，其余演示卡片不能混入真实记录。

## 8. 分批与验收

| 批次 | 实现者 | 独立评审 | 主要门禁 |
|---|---|---|---|
| B1 存储/迁移/只读API | store worker | runtime作者之外reviewer | CAS/哈希/绑定/故障/迁移保真/暂停owner |
| B2 工具/资源注册 | tool worker | store作者或专职reviewer | A05/06/07/11/13，真实T05容器 |
| B3 网关/预算/图/CLI | 主线程 | 专职reviewer，拆到≤约2000行 | A01～10/12，使用fake执行全部边界 |
| B4 前端 | 独立UI实现或主线程 | 非作者reviewer | A15真实SQLite/API，主题/键盘/axe/假数据隔离 |

A14单独用已有网关、公开/合成输入执行，保留安全摘要与完整用量；不能用fake或一次结构探针代替完整协作。真实上界依据或凭据缺失只阻塞A14，其他批次持续实施；未完成时父P0-05不能done。各批独立评审/修复复审、前端状态与开发历史、README及验收记录同步后才交付。

参考：LangGraph官方[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)；DeepSeek官方[token说明](https://api-docs.deepseek.com/quick_start/token_usage/)。框架循环次数限制只作兜底，预算/权限与最终状态由本项目执行控制器决定。

## 9. 单次输出配置补充

用户指出2,048过于保守，采用diagnosis/verification 4,096、repair 8,192，仍受Task Budget.output_tokens裁剪。输出截断不是结构纠错机会，保留合法usage后以固定MODEL_OUTPUT_TRUNCATED停止，不采纳半份建议；不自动扩大额度重投。A14检查finish_reason并记录实际用量，不能在没有实测时宣称性能不受影响。

第9节实现澄清：本批Edit.replacement仅为授权源码片段的临时替换建议，不能当成全文件替换或可应用patch；不臆补未读取的源码。P0-06需冻结范围/差异与完整文件保留验收后才允许应用。本批不改变T03四行授权范围。

真实模型首轮完整协作在验证阶段触及12次模型调用上限。修订宿主交接：每个角色的新上下文直接携带registry验证后的evidence_records（引用、摘要、findings），减少重复读取；不带前角色聊天、自述或replacement正文，源码仍仅T03授权读取。角色提示词v1.1显式使用已有证据，只请求缺失信息；总调用上限保持12。
