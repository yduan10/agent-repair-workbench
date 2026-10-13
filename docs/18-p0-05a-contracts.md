# P0-05a：角色、受控工具、状态和结果契约

2026-10-13。父任务P0-05；本批次先设计评审，再实现可执行schema、纯策略校验及只读能力目录。不实现模型推理、候选写入或后台任务恢复。

## 1. 交付边界

- 三个角色分别拥有严格输出schema；公共类型、工具参数和调度策略集中维护。
- 验证真实JSON边界：拒绝重复键、未知字段、非有限数字、超大消息和类型转换。
- 任务意图/状态转换及工具权限由程序校验。模型消息不含可自填的task_id、role、预算、根目录或最终通过状态。
- 新增只读 `GET /api/agent-contracts`，展示实际注册的角色契约与后续工具接口，支持查看/下载schema。标记 `runtime_available=false`，不把契约存在当成已接入执行。
- 本批次的结果存储/API是冻结规格；不创建空数据库表和假的Agent任务。P0-05b实际编排接入时实现存储/API并独立review。

## 2. 类型及版本

所有边界使用Pydantic严格模型，extra=forbid、strict=true、frozen=true；集合用有界tuple。JSON版本为严格整数1（不接受true）。对象ID使用规范小写UUID；摘要使用64位小写十六进制。不接收任意URL或宿主绝对路径。

### 宿主配置 TaskSpec

| 字段 | 规则 |
|---|---|
| task_id | 宿主生成UUID |
| intent | check_only / diagnose / propose_repair；P0-05拒绝verify_candidate |
| source_kind | synthetic / public_historical；本阶段不允许私有数据真实模型验收 |
| budget | total_tokens显式1..1000000，output_tokens显式1..32768且≤total_tokens；model_calls1..12，tool_calls1..20，candidates1..2，timeout_seconds1..600 |
| evidence | 1..32项任务授权的EvidenceRef，ID和sha256；重复ID拒绝 |

EvidenceRef只表达引用，不证明其真实存在或归属；宿主调用授权函数再次核对完整ID+hash及任务上下文。TaskSpec本身不会批准模型外发，既有01/17发送策略继续适用。

### 公共工具请求

schema_version、request_id、tool；工具名作为判别字段；无host权限字段。每工具参数严格且无任意shell/JSON透传：

| tool | 参数 |
|---|---|
| read_evidence | evidence_ref、section=summary/findings/events |
| read_contract | profile_id（有限标识符）、tool_name（有限标识符）、revision=sha256 |
| read_source | snapshot_id=sha256、relative_path、start_line/end_line正整数且跨度≤200 |
| check_contract | case_id=UUID、contract_revision=sha256 |
| request_reproduction | approved_case_id=UUID、profile_revision=sha256 |

路径仅接受POSIX相对路径，拒绝空段、`.`、`..`、反斜线、控制字符、绝对路径；只做词法检查不等于安全打开文件。真实T03仍必须无符号链接读取授权快照并检查摘要，留P0-05b/A11。

单请求/角色输出≤64KiB UTF-8、嵌套≤20；拒绝重复键、NaN/Infinity。解析失败只给固定错误码，不回显原文或Pydantic输入详情。

## 3. 角色输出与策略

每角色采用判别联合：`action=request_tool`或`action=conclude`。request_tool只携带上述一个请求（串行），conclude如下：

| 角色 | conclude输出 | 校验 |
|---|---|---|
| diagnosis | assessment=hypothesis/inconclusive、reason_code、evidence_refs | 没有confirmed/root_cause/pass字段；hypothesis必须附授权引用；最终证明由宿主证据校验产生 |
| repair | disposition=proposal_only/cannot_propose、evidence_refs、edits | proposal_only必须有1..5编辑和证据；cannot_propose没有编辑；每项path、base_sha256、replacement≤8192字符且合计≤32KiB UTF-8；重复path拒绝 |
| verification | assessment=needs_evidence/proposal_reviewed、reason_code、evidence_refs | proposal_reviewed必须有证据；不含candidate_verified/accepted字段 |

reason_code固定枚举：evidence_missing / contract_mismatch / serialization_mismatch / unsupported / proposal_requires_execution。没有任意自然语言报告字段，避免自动把模型回显的原始内容持久化。修复replacement属于不可信、仅临时内存中的候选建议，含原始内容风险，不进入本批API、日志或安全摘要；前端diff随P0-06专门设计。

允许工具：diagnosis/verification=T01..T05；repair=T01..T03。P0-05不注册T06/T07/T08。宿主从当前节点确定角色；authorize函数必须比较角色、已授权工具请求资源集和evidence引用。资源授权用精确请求目标键（包含版本），不能仅凭profile名称或UUID合法就授权。AuthorizationContext由宿主构造，含task_id、evidence_refs、allowed_targets与editable_files(path,base_sha256)。其task_id必须匹配TaskSpec；授权证据集合必须是TaskSpec证据子集。target_key为严格请求JSON去掉schema_version/request_id后的排序紧凑JSON的SHA256（含tool和全部参数），逐字匹配宿主登记的key；request_id不改变授权目标。repair conclude的每个编辑也必须匹配editable_files中的path+base_sha256。P0-05a只验证这些宿主注入的注册集，不宣称已查询物理产物；P0-05b网关再检查实际存在性/归属/摘要。工具响应payload在P0-05b随真实执行实现冻结，本批不声称完整T01～05协议或执行已完成。

去重/调度和真实工具执行属于P0-05b，不把本批纯校验当成已经实现exactly-once。

不同角色不能相互导入实现，公共解码入口显式选择宿主角色。无动态扫描/插件注册。

## 4. 前台任务状态

TaskState纯类型：task_id、intent、phase、revision、outcome。phase为queued/checking/diagnosing/proposing/reviewing/finished；outcome仅终态可设置。

允许边：queued→checking；checking→diagnosing或finished；diagnosing→proposing/reviewing或finished；proposing→reviewing或finished；reviewing→proposing或finished。全阶段可因取消/错误/预算停止而finished；finished不可再次转移；revision每次+1，expected_revision不匹配拒绝。check_only不能进入诊断；diagnose不能进入提案；只有propose_repair允许proposing，候选数量由P0-05b预算控制器在转移前限制。

终态结果：check_complete / diagnosis_complete / proposal_only / inconclusive / cancelled / failed / budget_exceeded / outcome_unknown。成功结果按意图与阶段匹配：check_complete只check_only的checking；diagnosis_complete只diagnose的reviewing；proposal_only只propose_repair的reviewing。需要证据支持的最终语义在P0-05b协调器验收，单纯状态枚举不能自证任务成功。

本状态不混用P0-04执行run状态/lease。模型不直接调用状态转移函数。

## 5. Agent安全摘要及后续存储/API冻结方案

本批定义 AnalysisSummary v1：task_id、summary_revision、source_kind、TaskState、started_at/finished_at（UTC、终态一致）、budget、usage、evidence_refs、execution_record_ids（≤20）、proposal_count、model_config_sha256（未调用可null）。不存源码、补丁正文、模型完整响应/提示词、密钥、原始值。usage为model_calls/tool_calls、reserved_tokens、known_input_tokens/known_output_tokens、usage_complete；真实金额先不支持，API返回null。调用中和缺usage都保留预留，不能当作已知消耗；比例与预算矛盾拒绝。Summary.task_id必须等于state.task_id；summary_revision独立递增且≥state.revision，state.revision仅在阶段转换时递增。known_input_tokens+known_output_tokens+reserved_tokens≤total_tokens；usage_complete=true时reserved_tokens=0，false时reserved_tokens>0；计数≤相应budget。model_calls>0必须有model_config_sha256，零调用则为null；proposal_count≤budget.candidates。时间必须UTC，终态有finished_at且不早于started_at，非终态不能有finished_at。

P0-05b写入设计：新增独立analysis_summaries表，不改旧run状态；字段task_id主键、summary_revision、summary_json≤256KiB、sha256、updated_at。复用既有SQLite连接事务/Alembic；v0002只增表；带数据降级拒绝，恢复按SQLite backup API。CAS更新只接受旧summary_revision+1；摘要与相关事件同事务。初次写入revision0，终态不可覆盖，幂等同revision+相同hash可返回原结果，同revision不同内容冲突。摘要和事件的中间模型内容只留内存。

执行记录关联必须在写入时检查存在性、任务绑定；既有run没有task_id，采用新增analysis_execution_links表，以record_id唯一绑定一个analysis，关联和摘要同事务。不能靠模型传入他人record_id获得证据。

API（P0-05b才实现）：GET /api/analyses?limit=1..50；GET /api/analyses/{uuid}；均只读，复用Host/Origin/no-store，参数错误只返回固定码。无库返回空列表，版本不支持/损坏返回503，不静默初始化。每条summary验证hash与schema；不返回原始存储错误。无POST执行/审批/取消。前台协调中断没有最终模型结论；重启显式对账标outcome_unknown，不自动续跑，禁止checkpoint重发。细节在实现前增量评审。

## 6. 本批API及UI

GET /api/agent-contracts 返回固定catalog_version=1、runtime_available=false、3个role(id、output_schema、allowed_tools)、5个tool(name、request_schema)、TaskSpec/TaskState/AnalysisSummary schema。仅表达契约可查看，不提供invoke端点，不加载env或模型，不创建状态目录。

前端工具接入页提供“协作接口”区域：角色横向tab、允许工具清单、折叠JSON schema及下载。保留现有MCP/Docker CLI入口。浅深色使用既有色板与字体，选择切换和折叠用短过渡，遵从reduced-motion；避免把接口目录画成已有运行状态。诊断/候选仍显示开发中与准确已完成基础，迭代历史追加P0-05a，不覆盖旧记录。

## 7. 本批测试与门禁

| 编号 | 测试 |
|---|---|
| C01 | 严格JSON、重复键、bool版本/数字、额外字段、超大/超深输入均拒绝且错误不含哨兵秘密 |
| C02 | 每角色正常/缺字段/不允许结论/越权工具；hypothesis必须引用宿主授权注册集中ID/hash匹配的证据；不冒充实际读库存在性检查 |
| C03 | 参数路径/行数/标识符/版本/超限边界，资源精确授权，合法UUID也不能跨任务访问 |
| C04 | 状态合法边/错误意图/终态覆写/CAS冲突；检查发现问题不导致propose意图提前check_complete |
| C05 | Summary终态时间/消耗预算/计数/引用/未知usage矛盾拒绝；不接受原始文本字段 |
| C06 | 所有角色schema与工具schema可导出；真实GET API无副作用，Host/Origin拒绝，未开放调用接口 |
| C07 | 真实API目录在页面显示、tab/折叠/下载、错误重试、移动/桌面/浅深色/键盘与axe；明确未接入执行 |

C01..C07是P0-05a实现门禁，覆盖A04/A05/A07/A11/A15的契约部分，不能替代A整项集成完成。更新pytest角色发现路径并collect-only；Ruff/mypy、已有API回归、TypeScript/build与相关E2E；独立代码审查及修复后复审。无执行器变更不必重跑全Docker矩阵。
