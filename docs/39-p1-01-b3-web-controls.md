# P1-01 B3：网页修复操作与本机常驻服务

2026-10-16。Feature P1。状态：planned → ready → in_progress → in_review → done。前置 B2 已验收并推送 `9195df9`；父任务 P1-01 保持 in_progress。

## 范围与交互设计

沿用 UI-08 的 Geist、中性浅深主题、现有 pane / btn / status 组件和配色变量。顶部紧凑操作区左对齐：案例、单/三角色、开始；下方简短限制及可展开预算。活动任务显示阶段、用量和停止，真实结构化事件用既有可收起控制台；diff/回归保留主区。移动端字段纵排，键盘焦点可见，沿用 reduced-motion。无需新插画、渐变或品牌重做。

```text
案例 [返回类型错误]  模式 [三角色]  [开始修复]
仅内置案例，候选留在隔离副本。   预算 ▸
运行状态 / 用量                              [停止]
结构化事件（可收起）
历史记录 | 候选 diff / 回归
```

## 执行与恢复契约

- POST 前 sessionStorage 持久化严格 request_id/case_id/mode；存储失败或损坏阻止启动，不静默删除。
- 刷新只 GET 查询 pending；404/超时/坏响应继续保留 ID，禁止自动 POST 或丢弃后新建。用户明确“重新提交同一请求”才 POST，并提示可能首次启动。
- 收到与 ID、案例、模式绑定的有效 receipt 才确认接收。终态且 active=false 才清除 pending；终态但待恢复仍占用，不宣称可重新开始。
- 同一页面双击有同步写锁；跨标签/进程由 B2 账本锁最终约束。sessionStorage 按标签保存，其他标签可从活动槽找回任务。
- GET 顺序轮询，每轮结束再计时，隐藏标签暂停；429 最多退避 5 次，失败保留已知状态并提供手动查询。POST 无自动重试。
- 停止操作绑定当前 receipt ID，确认后显式发送；只标记“正在停止”，直到真实终态。HTTP 未确认不推断远端停止。
- 事件 API 只返回已审计事件的 revision/time/kind/role/operation/tool/status/error 白名单；无 request claim、参数、正文或模型思考。新读取与既有槽共享容量。

## 验收与部署

浏览器覆盖正常启动/停止、双击、响应丢失、刷新、404 同 ID 重提、存储失败/损坏、绑定不符、CLI 历史不误取消、busy/recovery、浅深色/390与1440/键盘。增加真实 FastAPI+SQLite+确定性模型浏览器链路；不计真实模型修复效果，完整模型/Docker/审批验收仍属 B5。

用户追加要求前后端常驻：使用当前用户 launchd LaunchAgent，端口3010/8030，仅loopback；运行生产构建，不由聊天工具维持进程。配置文件和日志放本地忽略目录；凭据不放plist或版本库。先停写、SQLite一致性备份、显式0008迁移、逐表字节/行序核验，再启动。验证端口健康与launchd父进程，停止/启动命令写入本地指南。两份独立评审分别覆盖网页/事件与部署/迁移。

本批不实现人工批准/拒绝和补丁下载，留B4。未验收不得标网页可用。


## 实施与独立评审记录

- `frontend/lib/repair-runs.ts`：严格目录、receipt、事件契约；写请求不重试；同任务迟到响应不倒退revision，取消标志单调、已释放槽不复活。
- `components/repairs/run-controls.tsx`：顶部操作、会话pending、顺序查询、停止确认、真实结构化事件；预算折叠，响应未知不丢ID。
- `web_repairs` 新增有界事件读取，先在同一事务完整审计任务/事件/receipt，再投影白名单；共用读取容量，不返回私有request/claim。
- `ops/local_service.py`：固定两项macOS服务、配置权限校验、两项预检后安装、失败回滚本次注册、停止结果复核；不在启动时迁移或构建。
- 主库迁移在停写窗口持三种web owner锁，使用一致性SQLite备份。17张旧表183行包含BLOB与rowid逐项一致；reviewer独立比较原始tuple复验，0008新增接收表为空。

独立报告：[网页/事件评审](reviews/P1-01-B3-web-review.md)、[部署/迁移评审](reviews/P1-01-B3-deployment-review.md)。初审问题全部修复：历史通过误呈现、迟到回应撤销停止/终态、空串pending覆盖、T04错误标签；安装半成功、停止失败静默/跨checkout误停。另原页面axe回归发现环境链接只靠颜色区分，已加下划线并复跑通过。最终未关闭Defect P0/P1为0。

## 验收命令与实际结果

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv lock --check
# 此项使用独立临时SQLite与模型替身；执行前8030/3015必须空闲
AWB_B3_BROWSER=1 uv run --frozen pytest tests/test_b3_browser_live.py -q
cd frontend
npm run build
PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/repairs.spec.ts tests/repair-cases.spec.ts tests/repair-controls.spec.ts tests/b3-web-review.spec.ts
PLAYWRIGHT_CHANNEL=chrome npx playwright test tests/progress.spec.ts tests/reviewer-document-reader.spec.ts --grep '工作区共用外壳|all registered docs'
```

| 验证 | 实际结果 | 本地产物 |
|---|---|---|
| 全量Python | **1551 passed / 67 skipped**，218.58秒；1项既有多线程fork弃用警告 | `artifacts/b3-python-full.log` |
| 真实HTTP/SQLite/Next代理/Chrome | **1 passed**，4.1秒；刷新后模型边界总调用1次、停止持久化、未知用量保留 | `artifacts/b3-browser-live.log`、`artifacts/b3-browser-live-pytest-final.log` |
| 原修复页+B3浏览器 | **36 passed / 1 skipped**，21.4秒；浅深、移动端、axe、错误与迟到响应 | `artifacts/b3-final-browser.log` |
| 网页独立反例 | Python6项、Chrome6项通过，含历史通过与迟到响应 | `artifacts/b3-python-independent.log`、`artifacts/b3-web-independent.log` |
| 部署独立反例 | **23 passed**，权限、失败回滚、stop失败、未知launchctl状态、延迟卸载与持续占用 | 部署评审中的命令与结果 |
| 静态检查 | Ruff/格式405文件、mypy133源文件、uv锁78包通过 | 执行上方命令 |
| 生产构建 | 通过 | `artifacts/b3-build-delivery.log` |
| 文档链接 | Chrome 2 passed，工作区状态及133页、128个交叉链接，无断链 | `artifacts/b3-delivery-browser.log` |
| 绑定/CLI历史补充 | 2 passed，错误模式回执不确认、CLI-only不可网页取消 | `artifacts/b3-extra-ui.log` |
| 主库与launchd | 0008；17表183行保真；前后端PPID1、仅loopback、健康200 | `artifacts/b3-main-migration.json`、`artifacts/b3-independent-migration-proof.json`、`artifacts/b3-independent-launchd-proof.json` |

分组测试相互重叠，不累加为新的通过数。真实浏览器链路的模型与Docker是替身，未发真实模型请求或跑真实容器，不代表模型修复成功率；67个跳过包含显式浏览器门禁，该项另行启用已通过。前端跳过项为旧的显式门禁，不计通过。

最终常驻服务重启时发现launchd注册可能晚于bootout返回才消失；已加入最多50次、间隔0.1秒的状态复核（不含launchctl自身耗时），延迟卸载成功与持续占用失败两项回归通过。真实stop/install复跑成功，前后端PPID均为1，3010/8030仅loopback，页面、API及代理均200，见`artifacts/b3-launchd-delivery.json`。另补充rollback延迟卸载独立反例。上述全量Python结果产生于增加这三项运维测试之前；最终运维测试23项通过，未将分组测试重复累加。

失败记录保留：新增API测试初次默认TestClient Host触发403，改为本机Host；真实浏览器首次期待单独finished事件，而未知模型用量通过settled事件原子终结，改为核对实际settled、终态、停止标志和预留，未添加虚构事件；旧页面8个axe用例失败已修复链接样式。迁移首次检测到隔离测试API写者而拒绝，待其退出后执行通过，未放宽停写要求。

## 交付与后续

B2已推送`9195df96cc6e74aac5a7b2e07098e198a8c728e4`，CI run `38840999960` 成功。B3本轮尚未提交/推送。

本机前后端已由launchd常驻，入口`http://127.0.0.1:3010/workspace/repairs`。配置与日志只在被忽略的artifacts/local-service；不依赖对话进程，登录后自动启动，注销/睡眠/关机的系统限制仍适用。日志暂需手工归档，无自动轮转。服务停止/启动与升级命令见[本地指南](27-local-development-guide.md#网页修复与本机常驻服务)。

候选仍不写回用户项目。下一步B4：先冻结人工接受/拒绝与精确diff下载的版本绑定、幂等、CAS及失效规则，再实现；B5完成真实模型/Docker/网页/审批整体验收。父任务P1-01不能提前关闭。
