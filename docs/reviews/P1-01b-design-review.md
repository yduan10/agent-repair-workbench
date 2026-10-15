# P1-01b 网页分析控制台：独立设计预审

2026-10-14。评审者 `ui_review_density`，未参与本批实现。依据 [29](../29-web-analysis-console.md)、现有 `web_runs` 服务/账本、`AnalysisRuntime`、`AnalysisStore` 与任务所有权锁。

最终设计结论：**Pass，可按 B1→B4 分批实施**。初轮两个 Defect P1 设计缺口已补齐并复审关闭；实现阶段仍须逐项验证，不计功能已交付。原始发现保留如下。

## D1 — Defect P1：revision 0 不足以授予执行权限

设计提出先事务持久化 queued summary、created event 与接收记录，再调用 `run_created`。这是正确的接收顺序，但“初始 revision 0 且 registry 匹配”只能证明任务尚未进入下一阶段，不能证明调用者是这次首次接收的 owner。

故障窗口：事务已提交后、首次 phase 写入前宿主进程死亡；重启后读到完全合法的 revision 0。若同请求重复提交或恢复代码将读回结果交给 `run_created`，则它会被当成新接收执行。

最低要求：首次 `admit` 的新提交结果才授予仅当前 owner 可用的执行许可，重复读取/重复请求无许可；`run_created` 必须验证许可、task fence、任务 ID、初始摘要 hash 与 registry。可以通过明确的内部 admission claim/一次性 owner 回调实现，不需要新任务平台。不得仅依赖调用者约定不重试。

必测：提交成功但 202 丢失、提交后运行前 SIGKILL、同参仍 revision 0 的重放、错误 task/hash、已有 pending/finished、两个 worker。所有重放/恢复不得发出第二次模型或工具请求。

## D2 — Defect P1：明确活动槽释放的关联资源谓词

文档正确要求“终态且关联执行已确认结束”。现有 `AnalysisStore.reconcile` 只把分析转为 `outcome_unknown` 并保留预算，不检查 Docker，因此不能直接作为释放槽依据。

最低要求：持有网页 owner 锁并在事务中审核完整分析账本，逐一核对全部 `execution_record_ids`：

- 每条关联执行本身为终态；
- 最新 finished 且报告已校验、cleanup 为 removed/not_created、执行器已确认 absent；或最新 reconciled 且精确检查确认 absent/stopped；
- cleanup/create/attach 仍未知、执行器 unavailable、缺失/损坏报告或任一非终态均不释放；
- 无关联执行的分析终态可以释放本地槽，但模型用量未知仍保留，不能转写为零费用或调用未发生。

恢复应先明确处理分析与关联执行的对账，不把重启、取消请求或分析终态当作资源已回收。UI 的“需要恢复”给出具体入口或命令。

必测：分析已 unknown 但容器仍运行；多条关联仅部分回收；报告损坏；SIGSTOP owner仍活；恢复清理成功后才接收另一请求。

## 非阻断补充约束

- 前端在 POST 前持久保存安全的请求 UUID/固定 case/intent，刷新或响应丢失后恢复原请求；未知接收状态不能自动新建 ID。可使用 sessionStorage 或等效恢复机制，不能保存凭据或原始输入。
- 数据库以唯一/部分索引约束活动网页分析槽；锁顺序为网页 owner → task fence。取消只写持久取消标记，不等待长期 owner 锁。
- 配置检查不影响已接收请求的去重读取；模型缺失时 check_only 仍可用；catalog 不调用模型、不自动建库或镜像。
- 取消操作显示“请求已发送/正在停止”到真实终态。存在未知模型调用时继续显示未结算预算。
- 控制台按真实结构化事件展示，可跟随或暂停，有限高度、可切换结果；不伪造 stdout、模型思考或通用终端能力。
- B1/B2/B3/B4 分批与独立评审合理。本批直接网页执行不等同 P0-06 补丁已应用，父项完整 Web 审批仍未交付。

## 评审边界

这是设计预审，没有运行新代码或修改数据库，没有给运行性能、模型质量或生产交付出具通过结论。D1/D2 补文档并复审后，再由独立实现审查检验具体机制。

## 修订复审记录

已重新读取 29 规格“设计预审修订：接收权与恢复断言”：

- D1 关闭：首次提交独占 claim，DB 保存摘要/消费标志，重复请求没有执行权；原子消费 claim 与 queued→checking CAS，校验 fence 与初始摘要；覆盖创建后崩溃窗口。
- D2 关闭：遍历全部执行关联，终态、executor 确认、当前报告安全清理或显式资源 reconcile 缺一不可；明确分析对账不等于资源回收，并给恢复次序。
- 活动槽数据库唯一约束、锁次序与取消短事务写入已明确。
- 浏览器 pending 在 POST 前保存；未知状态刷新只查，显式重查复用同 ID；存储失败不启动，网络故障不清除并换 ID。

没有未闭阻断设计项。实现时重点核验 claim 消费和首次阶段事件必须同事务，后续模型发送必须位于其后；重复 cancel 不能触发第二个执行 owner。
