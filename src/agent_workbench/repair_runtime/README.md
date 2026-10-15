# P0-06 B3c：受控工具桥接

此批次连接已有账本、快照和宿主验收器；不包含模型循环、CLI 或网页执行入口。

## 调用接口

```python
bridge = RepairToolBridge(
    store=store,  # ReproductionStore，包含 T06/T07 基础方法
    registry=registry,  # 新任务的宿主审核资源
    baseline=baseline,  # SnapshotHandle
    snapshots=snapshots,  # SnapshotStore
    image_root=image_root,  # 显式准备过的固定镜像目录
    fence=fence,  # 调用者从创建任务到停止一直持有
    remaining_seconds=remaining,  # 本任务同一单调时钟截止时间
)
result = await bridge.execute(role, request, cursor=current_mutation)
current_mutation = result.cursor
```

控制器负责新建任务、模式选择、模型调用预算、停止和最后角色调度。每次工具调用前传入当前 `Mutation`（含 revision/hash）；返回的 cursor 替换旧值。bridge 同时只接受一次 execute；调用者不得并行运行模型/工具写操作。

## 执行顺序

- T01–T04：先账本预留，再调用已有 ToolRuntime 的只读路径。single 经新角色 schema 验证后使用 diagnosis 的只读权限适配。T05 不调用旧 AnalysisStore 执行路径。
- T05：先登记唯一 attempt，执行真实 oracle，再持久提交报告。只有实际 `observed_failure` 且版本核验通过才能解锁 T06；原始静态失败不是这个证明。
- T06：读取并重新核验本次会话的 T05 记录，再预留候选序号/claim。仅新 claim 可以创建隔离快照；失败也占候选额度。落盘结果不确定时停止，不自动再次应用。
- T07：由宿主生成 comparison ID 和四个 UUID，先原子登记。每个 oracle 结果先 `save_slot` 提交，再运行下一容器。`finalize_comparison` 从已保存的结果重新计算结论。

模型响应只返回已授权的源码/契约，以及固定规则计数、候选摘要和程序结论。隐藏 oracle 输入、step 名称和完整步骤列表不进入模型上下文。工具执行成功不代表候选通过；candidate_verified 仍不等于用户接受。

## 重复、中断和错误

- 同一会话记录完整请求摘要（包括 evidence_refs）。同 ID 不同角色或参数拒绝；任何 claim=None 都不会执行外部操作。
- 持久账本对 T06 的 patch/candidate、T05/T07 的宿主 plan 去重。它不保存完整模型请求/refs 字节；不能宣称跨进程能重建这部分比较。
- 修复任务禁止跨进程恢复执行。控制器重启只展示记录、释放旧所有权后显式对账；不得构造新 bridge 续跑已有任务。重建 bridge 不恢复 T05 的会话授权标记，重复读取旧 T05 不解锁 T06。
- 原生重复 cancellation 经过 owned/shield 等待子工作收尾。无法保存结果时 `requires_reconcile=True`，桥接拒绝继续调用；调用者须停止模型循环、释放 fence 后对账。未知写操作绝不重发。
- `requires_reconcile=False` 只表示没有已知 pending 需要对账，并非“任务通过”；控制器仍须处理 cancelled、工具 error 和 task.outcome。
- 不自动 build/pull 镜像，不接受任意路径/shell；保留 20 秒给创建确认、attach 回收、容器清理与收尾。跨进程的精确容器 inspect/reap 属独立恢复入口。

## 验证

```sh
PYTHONPATH=src python -m pytest tests/agents/test_repair_tool_bridge.py
AWB_CANDIDATE_DOCKER_TEST=1 PYTHONPATH=src python -m pytest tests/agents/test_repair_tool_bridge_docker.py
```

容器门禁必须先显式准备固定镜像。确定性测试使用真实 SQLite/快照和合成 OracleReport；两个 Docker 用例实际执行五容器闭环，分别验证正确补丁和常量返回回归。均不计入模型成功率或多 Agent 优势。

# P0-06 B3d：有限模型循环（内部入口）

`controller.RepairController` 连接上述工具桥接与修复模型适配器。仅提供 Python 内部
`await controller.run()`；本批不提供 CLI、API 或页面执行入口，不代表真实模型评估已经完成。

## 输入和执行权

构造参数是 `ReproductionStore`、`SnapshotStore`、已校验基线 `SnapshotHandle`、
`TaskResourceRegistry`、`RepairAdapter`、`single_role` / `three_role` 和预先准备的镜像根。
registry 必须由宿主加载固定公开 `output_mismatch` 案例、使用新 task UUID，意图为
`propose_repair`。已有任务（包括 pending、终态）一律不续跑；重建 controller 不重置账本。

整个新任务从 create 到停止持有同一 `RepairFence`。每次模型调用先事务预留 token、
次数与宿主生成的请求身份，再 send，最后 settle；未知用量保留预留并停止。
工具请求的 request_id 和 candidate_id 原样交给已审核 bridge 校验，不用新 ID 绕过去重。
context 中提供下一候选的确定性 ID 模板，但不能绕过快照/账本权限与最多两候选限制。

## 路由、上下文和边界

- 三角色由宿主按 T05 实际观察失败 → repair、T06 完成 → verification 调度；
  T07 拒绝且还有候选额度时回 repair。single 可用同一权限总集合，使用同一工具和账本。
- 两模式均使用同一 `Budget` 上限（12 模型、20 工具、2 候选、600 秒）与相同 8192
  单次输出上限；配置仍可收紧。工具保留收尾时间，不在剩余时间不足时启动外部操作。
- LangGraph 只持有 continue/end 路由标记，没有 checkpoint、模型原文或恢复能力。
  每轮上下文从 registry 核验引用、公开证据及白名单工具反馈重建；原角色聊天、候选
  replacement、隐藏 oracle 输入和步骤不传递给下一个角色。
- `needs_evidence` 停为 inconclusive；模型文字不能写 candidate_verified。
  该终态仅来自 T07 已持久化的宿主判定，且不代表接受或写回用户项目。
- 原生取消等待 owned 子操作退出；未知请求不自动重发。终态写失败、外部操作结果
  未持久确认时，返回 `requires_reconcile=True` 和最后已确认的 cursor。cursor 可能仍为
  ready/pending，不能将它解释为执行完成；释放 fence 后由独立恢复入口显式对账。
- 返回的 `RepairResult` 是宿主内部结果，包含 cursor、cancelled、requires_reconcile；
  它不是网页 DTO，不能直接公开序列化。错误仅使用静态错误码，不返回异常原文。

## 本批验证

```sh
uv run --frozen pytest -o addopts='--import-mode=importlib' tests/agents/test_repair_controller.py -q
```

使用真实临时 SQLite 与不可变快照，模型和 oracle 是明确的合成实现；验证单/三角色闭环、
拒绝后第二候选、共享预算、未知用量、调用前落库、取消、磁盘失败、权限拒绝和重复请求。
这些结果不计为真实模型修复成功率，也不支持三角色优于单角色的效果结论。
