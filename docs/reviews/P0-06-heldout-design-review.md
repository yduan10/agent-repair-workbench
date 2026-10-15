# P0-06 保留变体接入：独立设计审查

- 日期：2026-10-14。
- 作者：独立评审者 p006_contracts；只读当前规格与实现，本批没有改生产源码、CLI、案例、oracle 或主数据库。
- 依据：`docs/26-p0-06-candidate-verification.md`、registry、快照、T05/T07、controller、CLI、只读 API 与恢复边界。
- 结论：**建议采用“有限宿主 CaseProfile + 计数偏移保留变体”，分批实现后验收。** 本文是设计门禁，不是实现 Pass，不计算代码质量分数或模型成功率。

## 1. 验证的问题与不宣称的能力

现有开发案例在 `wrong_type` 场景把 count 转成字符串，确定性契约检查已经能发现类型错误。保留变体应让类型契约继续通过，而业务计数不正确，验证系统是否实际获取复现证据并修复业务语义。

这个变体仍是同一公开合成服务、同一函数、同一行为断言集，属于**不同故障类别的保留变体检查**。不能称为跨仓库、真实业务或通用修复泛化；独立评审者提供变体也不使它自动成为盲测。本文公开后实现者已知道故障，模型提示和修复逻辑不得因此加入该变体的答案。

发布判断必须分开：

1. 工程边界是否支持两个固定案例且不串联权限/版本。
2. 模型在冻结版本中是否成功修复各案例。
3. 单角色与三角色的描述性结果；每格 3 次不足以建立统计优势。

## 2. 评审者指定的保留变体

### 2.1 固定故障

建议 ID 为 `counter_offset`，保持 `lookup_result(count: int, scenario: str)` 签名和宿主授权范围不变。仅将该范围内的故障表达式换为：

```python
return {"count": count - 1 if scenario == "wrong_type" else count}
```

不改计数存储、非法参数拒绝、schema、传输、进程管理、`pass` 分支或函数外字节。可以在授权范围内将旧“serialization fault”注释调整为中性合成案例说明，避免给模型错误描述；不要在模型上下文直接告诉它“应该加一”或给出正确 replacement。

`wrong_type` 是现有执行场景枚举/容器 argv，不是新故障的产品名称。本批保留此执行开关，避免扩展镜像、容器入口和持久 slot 枚举。界面/报告用 `counter_offset` 标明案例类型，并说明底层仍使用既有受控场景。

### 2.2 冻结断言怎样识别它

现有 `SequenceOracle` 已冻结：一次 MCP 会话中合法 id=1、非法字符串、合法 id=0、合法 id=-1。合法调用 count 依次应为 1、2、3，非法输入不计数。

| 场景 | 实际返回 | 预期现有规则结果 |
|---|---|---|
| 原开发基线 / wrong_type | 字符串 1、2、3 | 三个合法步骤严格为 `count_type` |
| 保留基线 / wrong_type | 整数 0、1、2 | 三个合法步骤严格为 `count_value` |
| 两种基线 / pass | 整数 1、2、3 | 全部通过 |
| 正确候选 / 两场景 | 整数 1、2、3 | 全部通过 |
| 返回常量 1 | 后两次计数错误 | 不能通过 |
| 只改为 int(count - 1) | 类型正确、值错误 | 不能通过 |

**无需修改** `SEQUENCE`、输入/输出 schema、`SequenceOracle.run`、严格整数规则、非法输入断言、步骤集合或候选必须全部通过的门槛。只需要把“基线预期错误指纹”按宿主冻结案例精确选择。

### 2.3 初始证据必须诚实

新 envelope 中首个实际形态为整数 count=0，静态 schema 检查应显示通过。不得复制旧字符串失败 envelope 或伪造 `count_type` finding，以诱导模型进入修复。

若保存该初始 envelope 为手工合成输入，必须标注 synthetic，不能声称它来自真实运行。真实失败由 T05 在隔离容器执行后确认。进入 P0-06 的任务意图仍是宿主 `propose_repair`；初始静态检查通过不应跳过业务复现。冻结 prompt 1.4 不包含输入序列答案；当前已要求先 T05，应直接测试它是否足够。

## 3. 最小 CaseProfile：固定目录，不是任意插件

### 3.1 推荐结构

新增轻量宿主模块，例如 `repair_cases/profiles.py`，只含不可变类型、两个固定登记项和严格解析函数，避免依赖 registry/store/oracle 造成循环导入。

| 字段 | 含义 / 约束 |
|---|---|
| `case_id` | 封闭枚举：`output_mismatch`、`counter_offset` |
| `manifest_sha256` | 冻结资源 manifest 的 hash；旧项保留现有值 |
| `source_sha256` | 此案例基线完整 `server.py` 的 hash |
| `source_relative_path` | 固定 `source/server.py`，不接受模型/HTTP 路径 |
| `start_line/end_line` | 固定授权函数范围，仍是 107–110；AST 边界检查保留 |
| `envelope_sha256` / 固定 envelope 名 | 初始合成证据版本，不与另一个案例混用 |
| `failure_code` | 封闭为原案例 `count_type` 或新案例 `count_value`，仅宿主可见 |
| `profile_digest` | 对上述固定权限/判定元数据规范化摘要；用于实验清单和可信闭包 |

资源根由宿主把 case_id 映射到仓库固定目录，不能成为调用参数。建议新案例放 `examples/repair/counter_offset/`，内含独立 manifest、envelope 和源码；旧 `examples/analysis/` 完全保留。两份 manifest 必须唯一映射 profile，不接受未知 manifest 或重复登记。

**不要将整个 CaseProfile 放进模型上下文**：模型只需要授权资源标识、源码/契约、预算和真实执行后的安全反馈。预期失败步骤、隐藏输入、预期值、oracle 定义与 `failure_code` 不能作为待执行答案输入模型。

### 3.2 推荐函数边界（设计签名，尚未实现）

```python
def get_profile(case_id: RepairCaseId) -> CaseProfile: ...
def profile_for_manifest(manifest_sha256: str) -> CaseProfile: ...
def validate_baseline_binding(ref: SnapshotRef) -> CaseProfile: ...
def load_repair_case(
    case_id: RepairCaseId, *, task_id: str, budget: Budget
) -> TaskResourceRegistry: ...
```

前两个可放在无循环依赖的 profiles 模块；需要 SnapshotRef 的校验放独立绑定模块或快照层，避免 profiles 再反向 import snapshots。校验不止“manifest 存在”：baseline 必须与该 profile 的 source/file/tree hash 一致。candidate 的 file hash 是补丁后的值，必须沿其 baseline_tree_sha256 / manifest 追溯对应 profile，不能用候选自身 hash 选择故障类型。

P0-05 的 `load_case(output_mismatch|passing)`、原默认 registry 行为和现有工具 schema 不变。P0-06 新入口只允许两个固定 profile。不要为了新增案例，顺带开放任意 `root`、场景字符串或故障规则给模型/CLI。

### 3.3 最小持久化方案

优先复用已持久的 `SnapshotRef.manifest_sha256` 作为不可变 profile 标识，因 task、T05 plan、T07 plan 已嵌入基线；无需为了两个固定案例给旧 JSON 加默认字段或重写历史 SHA。

- 快照 create_baseline 接受宿主 case_id（默认旧值，旧调用保持兼容）。
- 快照 verify 从 ref 的已知 manifest 查回 profile，按对应固定源码复核；不能依赖进程“当前选中案例”。
- candidate 沿用 baseline manifest，禁止不同 profile 的 baseline/candidate 组合。
- 若后续证明必须显式持久 case_id/profile_digest，另立 additive migration 及旧库逐表保真门禁；不得直接改旧记录并重算 SHA。

## 4. T05/T07 的严格指纹绑定

### 4.1 当前承重位置

- `repair_store/reproduction_models.py::result_outcome` 当前硬编码三个合法步骤 `count_type`。
- 调用方包括 `repair_store/reproductions.py` 的 audit/finish、`repair_runtime/feedback.py`、`repair_runtime/tools.py::_require_observed`。
- `candidate_execution/compare.py::decide` 同样硬编码旧基线 `count_type`，且校验了四个槽的身份/版本、完整执行和清理。

### 4.2 适配规则

`result_outcome` 必须显式获取**持久 plan.baseline** 的绑定，不能从模型字段、环境变量或“当前 case”取规则。建议签名增加强制 keyword `baseline: SnapshotRef`；全部上述调用点传各自 record.plan.baseline。也可提供统一严格 helper，但不要保留一个新案例会误走旧默认的隐式 fallback。

共同规则：

1. baseline manifest/file/tree 必须对应一个固定 profile。
2. steps 名称/顺序恰为完整固定集合；三个合法步骤的 `(status, code)` 必须**精确**匹配当前 profile，其他全部 `(passed, ok)`。
3. report 绑定 plan 的 attempt、snapshot、suite、oracle、镜像、场景；版本前后有效、无 error、无 not_run、cleanup=removed。
4. T05 满足才 `observed_failure`；T07 还要求 baseline_pass 完全通过。
5. 两个 candidate 槽依旧全部通过；候选不允许以“符合预期失败”当成功。

**禁止**把旧 `count_type` 直接改为 `in {count_type, count_value}` 或“任意 failed 都算复现”。原开发基线出现 count_value、新基线出现 count_type 都必须判为 inconclusive/baseline_not_reproduced。这是增加两个互斥指纹，而不是放宽同一案例。

## 5. 准确改动范围与分批顺序

| 子批 | 文件 / 边界 | 必须保持 |
|---|---|---|
| H1：资源与快照 | 新 profiles/固定案例文件；`controlled_tools/resources.py` 宿主参数化及 P0-06 loader；`candidates/snapshots.py` `_frozen_source`、范围校验、create/verify | P0-05默认、字节范围/AST签名、软链接拒绝、原子发布、旧快照 |
| H2：指纹与账本接缝 | `reproduction_models.py`、`reproductions.py` audit/finish调用；`candidate_execution/compare.py` 精确profile指纹；`repair_runtime/feedback.py`/`tools.py` 同一绑定 | 原CAS/claim/预算/身份去重、候选验收规则、unknown不重试 |
| H3：运行入口与回归接缝 | `controller.py`/`tools.py` case_name固定检查改为严格profile一致性；`repair_runtime/cli.py`仅允许`--case`两个固定值；必要顶层CLI帮助 | prompt1.4、全部工具schema/权限、两候选/总预算、无自选path/scenario |
| H4：读接口/恢复/产品显示 | 现有 reader/recovery 验证不同manifest都有效；必要时从manifest导出安全案例名称，单独版本化DTO/前端适配 | 老JSON历史含义，当前版本失配处理，无新网页执行入口 |
| H5：真实评估 | 冻结源码/参数/模型/案例后，两个案例各单/三3次，交错次序 | 全部尝试入账，不跨版本拼接成功率 |

按约 2000 行/批独立评审。H4 若不增加DTO字段，可先在实验清单中显示 case_id，通过测试保证旧 reader/recovery 能正确解析两种快照；但产品不能把所有新记录继续标成旧字符串类型故障。

### 5.1 “冻结 oracle”版本陷阱

`ORACLE_SAFETY_FILES` 包含 `snapshots.py`、`resources.py`、`compare.py`、`cli.py` 等。接入 profile 会改变这些文件，所以 **ORACLE_SHA256 必然变化**；新增 profile/绑定模块若进入可信 import 闭包，也必须纳入内容摘要。不能为保持旧 hash 而删减闭包或排除新判定代码。

可保留的是 `SEQUENCE`、schema、断言语义与 `SUITE_SHA256`；适配后的完整可信实现需要新 oracle 摘要，并再次冻结、独立验收。旧报告原字节与 recorded_outcome 保留，当前复核按现有逻辑返回版本失配，不能重新贴上新版本 verified。

因此 1.4 旧开发案例的六次结果保留为历史开发轮；完成适配后需在同一新 oracle/代码版本重跑**开发案例六次 + 保留案例六次**，不能拿旧六次直接拼成同版本十二次公平集。镜像/launcher无改动时其 digest应保持。

## 6. 验收用例与实验门禁

### 6.1 确定性与故障门禁

| ID | 测试 | 预期 |
|---|---|---|
| H01 | 原P0-05两个case、原快照和旧账本读取 | 默认内容/能力不变，无迁移重写 |
| H02 | 未知case、伪manifest、源码哈希不符、越界函数/软链接 | 外部调用前拒绝 |
| H03 | 交叉使用A的manifest/B的source或baseline/candidate | 拒绝，不生成candidate_verified |
| H04 | 两case正确基线指纹互换、混合type/value、缺步骤、额外失败 | 一律不能observed_failure/verified |
| H05 | 两case完整正确指纹 | T05 observed_failure；T07还需baseline_pass |
| H06 | 常量1、int偏移、放宽schema、只修wrong_type破坏pass | 候选被拒；不能按成功数判定 |
| H07 | T05 evidence与T06、T07跨case/跨task交换 | ref/基线/版本绑定拒绝 |
| H08 | 新profile基线/候选篡改、版本漂移、unknown/取消 | 原拒绝/保留预算/精确回收语义不变 |
| H09 | 新case列表/detail/diff/比较与恢复读取 | profile从持久ref恢复，不依赖当前CLI参数 |
| H10 | 模型上下文抓取 | 无expected_failure、hidden steps/inputs/answers；不伪造静态finding |
| H11 | ORACLE闭包新增模块/内容变更 | hash变化；原SUITE及断言表达式未变 |
| H12 | 单/三同配置hash、同上限、全尝试账本 | 不能因case或mode放宽预算、权限、纠错次数 |

### 6.2 真实 Docker 先于模型

对两个 case 分别运行真实 T05；保留变体必须观测三个 count_value，pass基线全部通过。分别跑冻结四容器比较：一份人工正确候选应通过，一份看似修了类型但仍错计数的候选必须失败。人工候选只能计验收器测试，不能计模型成功。

旧代码回归和独立反例通过后，冻结清单包括源码、两个 case manifest/source/envelope、profile_digest、SUITE、ORACLE、镜像、模型配置hash、prompt1.4、预算和实验顺序。

### 6.3 模型保留检查纪律

- 开发案例和保留变体在同一适配版本运行；顺序预定，单/三交错，各3次。
- 不根据保留变体结果调整 prompt、源码错误幅度、初始证据或选取更容易成功的variant。
- 所有错误、提前结束、未知用量、超时都保留；终止条件按当前宿主预算，不额外补一次直到成功。
- 每次记录case/mode/task/config+oracle+suite hashes、最终状态、模型/工具次数、候选数、tokens及未知预留、时间、四槽结果。无价格配置则费用未知。
- 如果暴露工程缺陷需要修复，旧轮完整标注被工程缺陷影响；新版本重新冻结，不能筛掉失败后与新成功混算。此时该变体已参与开发，下一次再声称“未调参保留检查”需要新的独立变体。

## 7. 风险、实施条件与最终建议

| 风险 | 必须满足的设计条件 |
|---|---|
| 引入profile变成任意代码平台 | 只登记两个宿主案例，拒绝任意root/manifest/规则输入 |
| 规则放宽导致假复现 | 精确manifest→单一失败指纹，不允许type/value并集 |
| 历史验证标签错误沿用 | 新oracle摘要；保留历史与当前核验分离 |
| 合成业务错误被包装成真实需求 | 明示同服务不同故障，泛化结论不成立 |
| 评估集泄漏和反复调参 | prompt1.4冻结，独立变体预先定义，完整轮次留存 |

**实施建议**：先 H1/H2 的固定案例和判定接缝，再 H3/H4 回归，最后 H5。上述边界可满足 doc26 的独立保留变体要求，同时不必改变候选行为断言、镜像或工具权限。全部完成前 P0-06 保持 in_progress。本文不批准任何代码上线，也不替代实现后的独立评审。
