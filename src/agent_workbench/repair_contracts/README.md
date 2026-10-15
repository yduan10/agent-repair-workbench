# P0-06 模型决策契约（B3a）

本目录是模型请求的结构边界，不执行工具、不记账、不宣称修复闭环已接通。旧 P0-05 的 decoder、角色契约、提示词和 `proposal_only` 含义保持不变。

## 集成接口

- `codec.decode_role(raw, role)`：复用既有 bounded decoder，返回角色受限的输出；未知角色和非法 JSON 只返回固定错误代码。
- 各 `agents/<role>/repair_contracts.py` 导出 `ADAPTER` 供模型网关构造输出 schema。
- `tools.ApplyCandidate` / `tools.CompareCandidate` 是 T06/T07 类型；T01–T05 使用原类型，不复制字段。
- 提示词分别在各角色 `prompts/p006.txt`，当前版本 1；单角色对照组单独维护 `agents/single/`。

## 权限

| 角色 | 允许工具 |
|---|---|
| diagnosis | T01–T05 |
| repair | T01–T03、T06 |
| verification | T01–T05、T07 |
| single | T01–T07 |

工具 schema 仅接受各角色的权限子集。单角色权限是三角色并集，实际任务总预算及模型配置必须由运行器保持一致。

`RoleConclusion` 仅包含 `action=conclude`、`disposition=handoff/needs_evidence`、固定 `reason_code` 和证据引用。handoff 必须带证据；它不能指定下一角色，也不是成功状态。needs_evidence 由宿主收束到 inconclusive。reason_code 仅允许 evidence_missing、contract_mismatch、serialization_mismatch、unsupported、candidate_requires_comparison、comparison_requires_review，不承载自由文本。

## 宿主必须继续执行的校验

类型正确不代表授权成功。运行器仍必须检查 task/request/candidate 归属、证据存在性和版本、预算与去重、候选序号以及只读快照。T06 函数体/AST 白名单由 SnapshotStore 校验；结构契约只保证 UTF-8 片段不超过 8 KiB、无 NUL、标识符及引用有界。模型不能指定路径、容器身份、suite/oracle/image 版本、资源预算或最终判定。

仅宿主可写 candidate_verified；接受候选由用户另行决定。请求原文、replacement、模型原始输出是临时内存数据，不能整对象写入日志/账本。存储只保留宿主批准的字段与摘要。
