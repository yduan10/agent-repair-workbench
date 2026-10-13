# P1-01a：网页受控复现与运行操作

设计日期：2026-10-13，完成日期：2026-10-14。状态：done（实现与验收见[23](23-p1-01a-delivery.md)）。优先级：Feature P1，依据用户本轮操作性要求提前；父任务P1-01及P0-05b不据此完成。

## 1. 目标与顺序调整

用户指出运行页以ID、时间、事件和下载为主，不能使用已经完成的CLI复现能力。本批将P1-01拆出P1-01a，依赖P0-03/04即可开始；模型协作、候选编辑和审批仍依赖P0-05/06。

交付路径：选择审核过的故障场景 → 检查本机准备状态 → 点击开始 → 查看真实执行进度 → 必要时请求停止 → 阅读经过结构与SHA核验的报告 → 下载配置/复制CLI命令。

采用已有Docker执行器、SQLite与确定性检查器。首批仅正常调用、工具错误、调用超时、响应丢失四种合成场景，明确标注来源。不提供任意shell、argv、环境变量、代码上传或模型外发。进度控制台展示真实结构化事件，不伪造终端stdout。

## 2. HTTP契约

接口均经现有loopback Host/Origin边界；新增写接口要求准确的本地前端Origin、application/json、4KiB体积与5秒读取上限，拒绝重复键、非法JSON、额外字段。错误只返回固定code，不回显原值/堆栈。URI与读写路由通过Next白名单转发。

| 接口 | 输入 | 成功输出 | 错误 |
|---|---|---|---|
| GET /api/reproductions/catalog | 无 | version=1、4个cases、ready、reason（可空）、active_run_id（可空）；case含id/title/description/expected，只含已审文案 | 准备问题以ready=false和固定原因表示；不隐式初始化DB或prepare/pull |
| POST /api/reproductions | request_id（规范小写UUID）、scenario（4枚举） | 首次202 {run:RunView,reused:false}；同请求200 {run,reused:true} | 400非法输入、403来源、409请求冲突、410旧映射的记录已清理、429槽忙、503准备/存储问题 |
| POST /api/reproductions/{run_id}/cancel | 空JSON对象 | 202 {run_id,status:cancel_requested}；已结束200 {run_id,status:already_finished} | 404非本入口任务、400非法输入、503存储问题 |

两条写接口还共同返回 408（读取请求超时）、413（请求超限）、415（不是 application/json）；不回显请求内容。

创建固定profile=isolated-fixture、seed=0、lifetime=45；固定case为仓库examples/mcp/lookup-case.json（lookup参数id=1）。规范化请求摘要包含配置、case摘要与Web契约版本，不能只比较scenario。准备状态仅在新请求创建时再次验证；已有request_id的200/409/410判定先于准备检查，即使Docker不可用也可获取既有结果。

已有GET /api/runs、详情与report继续兼容。网页通过这些接口轮询真实状态，不增加另一个内存任务账本。写响应丢失后按同request_id查询或重放接收请求，只能返回已存在任务，不重新执行。

## 3. 持久接收、并发与故障窗口

- 新增SQLite web_requests表：request_id为主键，严格等于run.run_id（响应丢失可GET /api/runs/{request_id}）；保存payload_sha256、active、cancel_requested；不使用随run删除的级联外键。active=1使用部分唯一索引，保证跨进程最多一个Web运行。
- 在同一个BEGIN IMMEDIATE事务中检查重复请求、槽占用、创建run、claim生成attempt/lease、保存web映射；提交后才允许执行/返回202。已有同请求先返回，不受其他任务槽忙影响；异payload始终409。
- API lifespan持有独立接收/执行worker，HTTP取消不能中断admit到worker注册。私有claim token仅宿主持有，不进入API/日志。
- 同一记录只领取一次。强杀在提交后/调度前会留下running，不能因为重启或重复POST自动分派。120秒lease后用户显式运行现有CLI runs reconcile核对；不能把未见结果当未执行。
- 取消是持久标志，由所属worker有界轮询并触发AnyIO取消作用域；在执行开始前也必须读取标志。跨API进程请求停止仍有效。完成/取消竞态以真实runner报告为准。
- runner调用已发出后，取消可能得到outcome_unknown。仅完成清理、保存终态与报告之后才释放Web槽；取消接口成功不等于运行已取消。
- 保存失败或清理不明确时保留槽。下次新接收可以基于已持久化的安全终态/资源清理证据，或者显式reconciled且容器absent/stopped的证据释放旧槽；无证据保持阻塞并指引CLI核对，绝不重投旧任务。
- prune排除active Web记录。非active运行清理后保留web_requests墓碑，旧ID同payload返回410，异payload返回409；不能重新执行。空库降级检查含新表。
- 停服停止接收、请求已有worker取消、等待有界清理/保存；强杀仍靠已有容器watchdog和显式对账。
- Web单槽不宣称限制用户另行启动的CLI并发，也不提供任意外部工具exactly-once保证。
- 新Web接收至dispatch、执行、cleanup、finish全程持有状态目录内跨进程非阻塞排他flock，进程退出由OS释放。已有请求只读重放不需锁，cancel写flag不抢owner锁。暂停但存活的owner仍持锁，lease过期不能绕过它接收另一任务。
- 显式CLI reconcile涉及active Web记录时，必须先非阻塞获得同一owner锁，并持锁至实时资源核对与状态事务完成；拿不到锁则保留原状态，不把absent记为安全。后续admit释放旧slot也须持有该锁并核对持久记录。测试覆盖旧owner暂停/lease过期/第二owner核对和接收/旧owner恢复。当前支持macOS/Linux；不支持flock的平台明确拒绝网页执行，不降级成无锁。

## 4. 迁移与准备

迁移0002保留已有运行/事件/报告。读接口不偷偷迁移；新旧schema判断、显式runs init升级、已有数据备份/还原、拒绝未知版本和带数据降级必须测试。生产本机迁移前通过现有备份方式保存数据库，不输出数据内容。

GET目录只读取/核验镜像manifest、源码摘要、Docker及数据库状态，不build、不pull、不执行fixture、不创建数据库。网页明确展示未准备原因及文档入口；用户显式初始化/准备后重查。POST创建时重新核验准备条件，失败不得执行容器。

## 5. UI和命令区

沿用frontend-design设计规则及现有浅/深/系统主题。首屏先给“新建受控复现”，随后历史列表和所选运行；不再把UUID作为主要内容。

- 场景说明含预期结果、合成来源、固定参数与执行边界；Start/Cancel有独立pending态和双击保护。
- Start的request_id在网络不确定时保留；刷新/重连只查任务和槽，不自动重新提交。显式新建始终生成新ID，与重放原接收请求分开。
- 过程区按created/claimed/finished/reconciled显示时间与状态；正在运行自动刷新，离页停止读取，已有服务任务继续。取消失败不伪造已停止。
- 报告先经过既有完整schema、run/attempt关联及原始字节SHA校验，再显示问题代码/JSON路径、输入输出检查、耗时、资源回收。坏报告禁止展示“通过”。
- ID、版本、指纹、lease收进“技术详情”；保留可复制信息供排查。列表主文案为场景、结果、时间。
- 命令区展示真实CLI命令；下载固定JSON配置并提示保存至项目根目录，复制命令引用该文件和固定case。不是网页shell终端。对历史记录只能称“同场景新建”，旧记录未保存完整配置，不能声称原样重放。
- 当前运行可取消；取消资格以只读catalog.active_run_id为准；仅该ID匹配且未结束时出现停止按钮，旧CLI记录不出现伪造的可取消按钮。未知结果提示先核对，不自动重试。
- 支持空态、准备缺失、API故障、槽忙、无报告、断线、取消中、结果未知；操作后明确下一步。

## 6. 测试矩阵与门禁

| 编号 | 范围 | 必须的输入/预期 |
|---|---|---|
| W01 | 输入边界 | 非法UUID/场景、未知字段、重复键、过大/慢体、缺Origin/跨站均拒绝且无执行 |
| W02 | 原子接收 | 两进程同ID仅一个run/attempt；异ID最多一个active，另一个429；不同payload409 |
| W03 | 幂等 | 202丢失、HTTP断开、重启后同ID只返回原记录；不会再调用runner |
| W04 | 崩溃 | admit提交前回滚；提交后未dispatch保留记录，重启不投递；暂停旧owner+过期lease不得由新owner接收；持存活锁实时对账后才可解除占槽 |
| W05 | 取消 | 开始前/调用后/完成竞态/重复cancel/跨进程cancel；已发调用不伪装无副作用 |
| W06 | 保存与资源 | claim/finish/SQLite busy/清理未确认都不重复执行；失败保存保持槽 |
| W07 | 墓碑和迁移 | 老库升级保真、备份恢复、拒绝未知schema/带数据降级、active不prune、prune后重放410 |
| W08 | 准备 | GET无执行/创建DB，POST重验，Docker/镜像未备好正确失败且不下载/构建 |
| W09 | 实际容器 | 显式Docker门禁逐个执行4场景；报告与持久记录关联、成功/失败/未知语义和回收证据正确 |
| W10 | 网页操作 | 真实API开始→查询→报告；槽忙/断连/重复点击/取消/离页/跨选项迟到响应；不得伪造即时成功 |
| W11 | 报告命令 | 坏SHA/双ID/畸形JSON拒绝展示；CLI下载配置与复制命令一致、同场景说明、ID折叠 |
| W12 | UI质量 | 浅深色/手机/键盘/axe、状态播报、命令局部横向滚动；既有读接口/下载/草稿导航回归 |

确定性测试用fake执行器断言控制行为，不能替代W09真实Docker与W10真实API；skip单独报告。按后端状态与并发、API与执行生命周期、前端操作/报告三个批次独立评审，每批约2000行以内。所有阻断发现修复复审后才done。本规格保留验收要求；实际命令、结果及各门禁的证据类型见[23](23-p1-01a-delivery.md)。

## 7. 下一步

本批形成可操作的受控复现入口后，继续P0-05b模型网关、T01～T05真实工具、预算、有界协作与安全摘要存储；模型正确率/修复率仍需后续独立评测，不用本批合成复现率替代。
