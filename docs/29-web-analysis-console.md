# P1-01b：页面执行控制台与受控分析

2026-10-14。状态 planned → ready → in_progress → in_review → done；交付与独立复审见 [30](30-web-analysis-delivery.md)。用户明确要求诊断及工具接入页面直接执行，不能仅复制 CLI。此增量提前接通已验收 P0-05 能力，P0-06 继续按原批次开发，不等待其全部完成，也不宣称建议已应用。

## 目标与入口

诊断页提供案例、分析目标、开始、停止及实时控制台。案例仅为已审核的 `output_mismatch` / `passing`；目标为 `check_only` / `diagnose` / `propose_repair`。工具接入页可直接运行已有受控 MCP 容器检查，通过原 `/api/reproductions` 服务；同时提供进入分析控制台的入口。终端显示实际阶段、工具与消耗事件以及可打开的结果；命令用于说明当前操作，可复制，但不能输入任意宿主 shell。错误、取消请求与真实终态分开显示。

## HTTP 与接收契约

- `GET /api/analysis-runs/catalog`：固定目录、模型配置是否就绪、执行槽状态。不泄露网关地址、密钥或完整环境。
- `POST /api/analysis-runs`：严格 `{request_id, case_name, intent}`；固定预算复用 P0-05，拒绝额外 URL/路径/模型名/原始证据/命令字段。
- `POST /api/analysis-runs/{task_id}/cancel`：严格空对象，持久请求停止。
- 结果使用现有 `GET /api/analyses/{task_id}` 和列表；页面按任务 ID 轮询，显示真实结构化事件，不构造 stdout 或模型思考文字。
- 沿用 loopback Host、精确 Origin、JSON/4KiB/5秒读体、no-store 和静态错误码边界。

先查去重，再查运行配置。同 ID 同参返回原任务；异参409；分析已清理但墓碑还在410。刷新/丢响应后重用同一request_id查询，绝不自动生成新ID重试。只有用户明确新建才产生新ID。

## 存储及所有权

additive migration 0007 新增 `web_analysis_requests`：request/task ID、规范请求hash、case/intent、固定接收策略hash、active、cancel_requested。旧分析 schema 和所有既有表内容保持原样。

接收顺序：全局网页分析 owner lock + task AnalysisFence → 校验固定资源/配置 → 单一SQLite事务创建初始summary、created event、接收记录 → 已注册lifespan owner继续持锁 → 返回202 → 开始模型/工具。不得先返回202再创建分析。旧CLI继续持task fence创建并执行，同一执行体需严格验证新建revision0与registry匹配，不能用它恢复finished/pending任务。

网页分析使用独立 `analysis-web-owner.lock`，同时最多1项网页分析。已有网页复现仍最多1项，允许两类各一项同时运行，各自遵守资源上限；不引入共享任务队列或多租户承诺。一个分析内部的工具保持串行。SIGSTOP仍持锁；SIGKILL后接收墓碑/summary/预留留存，恢复只对账，不能续跑。

活动槽仅在终态且关联执行已确认结束时释放。遇到孤立活动任务返回recovery_required；分析outcome_unknown不能等同容器已清理。沿用显式analysis/run reconcile与精确资源检查；不能重启即释放未知槽。

## 停止、关闭和预算

停止先写取消请求，owner监视后取消执行；UI显示“正在停止”直到实际终态。接收后首次模型前的取消应为0模型调用。模型已发送而响应未知保留预留，不能显示零消耗。HTTP断开不撤销已接收任务。API关闭停止接收、取消并等待既有有界回收和持久终态；重复取消不会释放执行槽或制造新任务。

生产模型配置仅来自API进程环境，catalog报告缺失时模型按钮给出明确配置说明，check_only仍可执行。实际模型外发只来自审核registry；网页导入的个人记录不能通过此入口外发。测试fake adapter仅构造注入，不开放API开关。主库升级必须先停写备份、逐表保真核对；开发验收在独立临时库。

## 页面设计

沿用UI-07主题和信息层级，执行区在首屏，占用紧凑一段。控制台使用等宽事件行和时间，有限高度；提供跟随最新/暂停跟随，运行中停止和打开结果。展开技术信息才显示ID和恢复命令。浅/深色与reduce-motion保持一致。配置未就绪、服务断开、运行中、停止中、成功/失败/未知均有明确可行动状态。结果与完整历史继续可检索。

## 验收与分批

| 批次 | 门禁 |
|---|---|
| B1接收账本/runtime拆分 | 原子提交、同参复用/异参冲突/墓碑、持久取消、0006→0007保真、CLI旧行为、非初始任务不可重入 |
| B2服务/API | 两worker竞争、HTTP断开/响应丢失、接收前失败零调用、调用前/中/T05停止、shutdown、owner暂停/死亡、未知资源不释放槽、权限与泄漏 |
| B3前端控制台 | 真实隔离API+SQLite开始/阶段/停止/刷新/断网、重复点击、按钮状态、键盘浅深390/1440、独立UI评审 |
| B4真实验收 | check_only真实运行、现有模型一次真实分析；T05实际Docker；全部尝试保留，不把fake当真实效果；能力/历史/文档同步 |

分批约2000行以内，实施者与reviewer分离；未闭Defect P0/P1不得完成。P1-01父项的完整补丁审批仍按P0-06后续计划。

## 设计预审修订：接收权与恢复断言

- admit 仅首次事务提交返回私有一次性 claim token，数据库只存摘要及 consumed 标志；重复请求只返回历史且无 claim。run_created 必须核验 task fence、初始summary hash、未消费claim，并在单一事务消费 claim + CAS queued→checking；即使重启后摘要仍revision0，旧/重复请求也不能领取执行权。旧CLI使用原自建入口，不暴露网页claim绕行路径。
- active=1 由数据库部分唯一索引约束。锁顺序固定网页分析owner→task fence；cancel只有短事务，不等待长期owner锁。
- release_safe 遍历 summary 全部 execution_record_ids，每一条必须为终态且 executor 明确 absent/stopped，并有当前最终报告 cleanup 安全或显式reconciled资源确认；任一运行缺失、非终态或清理未知均不释放。分析reconcile仅标记unknown，不能替代关联运行资源对账。页面恢复指引先核对关联运行及资源，再对账分析，最后刷新槽状态。
- 浏览器在POST之前持久保存安全pending `{request_id,case_name,intent}`；存储失败不启动新任务，提示恢复存储或使用CLI。未知提交状态刷新后继续查询相同ID，不自动重新提交；显式“重查本次提交”才可使用同ID幂等POST。清除pending前必须已得知终态或明确未接收，不能在网络异常时生成新ID。
