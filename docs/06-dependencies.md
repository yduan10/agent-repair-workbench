# P0-01 依赖记录

记录日期：2026-10-13；Python 3.12.13；uv 0.11.11。版本取本次 uv 生成的锁文件及实际安装元数据，不手改锁文件。许可证字段取已安装 distribution metadata，仅说明依赖本身，不为本项目选择开源许可证。

| 依赖 | 锁定/固定版本 | 用途 | 许可证 |
|---|---|---|---|
| pydantic | 2.14.1 | 严格 envelope 与报告模型 | MIT |
| jsonschema | 4.26.0 | 官方 Draft 2020-12 验证器；multipleOf 做局部精确数值扩展 | MIT |
| pytest | 9.1.1 | 确定性行为与集成测试 | MIT |
| hypothesis | 6.169.0 | 路径转义、整数边界性质测试 | MPL-2.0 |
| ruff | 0.17.0 | lint / format | MIT |
| mypy | 1.20.2 | 严格静态类型检查 | MIT |
| types-jsonschema | 4.26.0.20261006 | jsonschema 类型声明 | Apache-2.0 |
| hatchling | 1.32.4 | 构建后端（build-system 精确版本） | MIT |

运行时仅前两项；测试工具不参与最终业务调用。构建后端在隔离构建环境使用，未装入项目运行环境；构建环境的传递依赖需在正式分发门禁中另行固定和扫描。当前只交付本地源码开发状态，未发布 wheel 或公共软件包。

## 已执行的安全检查

```sh
uvx pip-audit --path .venv/lib/python3.12/site-packages --format json --output artifacts/dependency-audit.json
```

实际输出：`No known vulnerabilities found`。报告包含 24 个条目：23 个环境依赖已检查、0 条已知漏洞；本地 `agent-workbench==0.1.0` 不在 PyPI，跳过公告查询，源代码由独立 reviewer 审查。原始扫描文件在忽略的 artifacts 目录；该扫描不覆盖未来依赖、构建隔离环境或未知漏洞。

Actions 通过官方远端 tag 查询固定为 commit：checkout v4 → `11d5960a326750d5838078e36cf38b85af677262`；setup-uv v6 → `d0d8abe699bfb85fec6de9f7adb5ae17292296ff`。CI 权限 contents:read、不保留 checkout 凭据、任务限时 10 分钟。远端 workflow 尚未运行。

## 升级与退出

升级需读变更说明、由 uv 重新生成锁、运行固定回归及数值/拒判用例、审查锁文件变化。jsonschema 扩展只覆盖 multipleOf，并明确检查嵌套 `$schema` 不绕过扩展；升级必须保留该回归。遇到包弃养时先维持最后验证版本，替换计划作为独立任务，不临时手写完整 schema 引擎。

## UI-01 依赖增量（2026-10-13）

前述 P0-01 表是历史快照，当前运行时增加下列依赖。Node 24.15.0 / npm 11.12.1；JS 精确解析版本以 frontend/package-lock.json 为准。

| 依赖 | 实际版本 | 用途 | 许可证 |
|---|---|---|---|
| FastAPI | 0.143.0 | 本地 HTTP 薄适配层 | MIT |
| Uvicorn | 0.54.0 | ASGI 服务 | BSD-3-Clause |
| Starlette | 1.7.0 | FastAPI 传递依赖 | BSD-3-Clause |
| AnyIO | 4.15.1 | ASGI 异步生命周期 | MIT |
| httpx | 0.28.1 | API 集成测试，开发依赖 | BSD-3-Clause |
| Next.js | 16.4.0 | 产品网页与同源代理 | MIT |
| React / React DOM | 19.3.0 | 交互界面 | MIT |
| Zod | 4.6.7 | API 报告客户端验证 | MIT |
| lucide-react | 1.55.0 | 矢量功能图标 | ISC |
| Tailwind CSS | 4.3.3 | 样式基础 / 构建 | MIT |
| Playwright | 1.64.0 | 真实浏览器验收 | Apache-2.0 |
| axe-core | 以 lock 为准 | 可访问性自动检查 | MPL-2.0 |

本轮 `uvx pip-audit --path .venv/lib/python3.12/site-packages --format json --output artifacts/dependency-audit-ui.json`：36 个环境条目，35 个查询公告，本地项目跳过公告查询；0 条已知漏洞。`npm audit --json`：0 条已知漏洞。扫描只反映当前公告与依赖树，不是全产品安全结论。

新增 Actions setup-node v4 官方 tag 固定为 `49933ea5288caeca8642d1e84afbd3f7d6820020`。已配置独立 product-ui CI job（npm ci / build / typecheck / Chromium / E2E）；尚未推送和运行远端 CI。代码整理使用临时 Prettier 3.6.2，不作为产品运行依赖。

Starlette TestClient 对 httpx 发出弃用提示，当前测试仍通过；后续依赖升级需要迁移测试适配，不能隐藏警告冒称未来兼容。


## P0-02 依赖增量（2026-10-13）

通过独立兼容实验后，主项目固定 `mcp==2.3.0` / `mcp-types==2.3.0`（MIT）；新增 httpx2/httpcore2、cryptography/cffi、PyJWT、python-multipart、sse-starlette、truststore 等传递依赖，具体版本由主 `uv.lock` 冻结。此前 FastAPI/Pydantic/jsonschema 版本未变。

- 主环境：`uvx pip-audit --path .venv/lib/python3.12/site-packages --format json --output artifacts/dependency-audit-mcp.json`。47 条环境依赖记录，46 项查询公告，本地项目跳过；0 条已知漏洞。
- 公开历史案例：独立 `experiments/public_mcp_case/uv.lock`，SDK 源码来自固定提交，不将该历史源码包安装进主环境。`uvx pip-audit --path experiments/public_mcp_case/.venv/lib/python3.12/site-packages --format json --output artifacts/dependency-audit-public-case.json`：26 项已安装依赖，0 条已知漏洞；固定源码单独由代码审阅与归档完整性核验覆盖，公告扫描不替代源码审核。
- Python SDK 升级必须重新跑握手版本、输出验证钩子、missing/null、取消与进程清理测试，以及公开案例。未知漏洞、进程沙箱和源码并发篡改不由本次扫描保证。

## P0-03 执行环境增量（2026-10-13）

未增加 Python/Node 包依赖；Docker 通过 argv CLI 调用，固定官方基础镜像以完整 digest 和本次 iidfile 标识。
当前本机验收环境：Docker client 29.7.1、Colima Linux daemon 29.5.2、Linux arm64/cgroup v2；
基础镜像 Python 3.12.14（宿主项目 Python 3.12.13）。运行期不下载镜像或依赖。
实际 image ID/source 摘要保存于忽略的 `artifacts/p0-03-image.json`；镜像升级须重新准备与完整故障验收。
本里程碑没有执行镜像 CVE 扫描，不将既有 pip/npm 公告扫描结论扩展为容器镜像认证。


## P0-04 持久化增量（2026-10-13）

| 依赖 | 锁定版本 | 用途 | 许可证 |
|---|---|---|---|
| SQLAlchemy | 2.0.54 | SQLite 事务、条件更新与表定义 | MIT |
| Alembic | 1.20.0 | 版本化 schema 升级与空库降级 | MIT |
| Mako | 1.4.3 | Alembic 传递依赖 | MIT |
| MarkupSafe | 3.0.4 | Mako 传递依赖 | BSD-3-Clause |

没有增加数据库服务、队列或 Node 依赖；SQLite 由 Python 标准库提供。
锁文件由 `uv add` 更新，`uv lock --check` 通过。
`uvx pip-audit --path .venv/lib/python3.12/site-packages --format json --output artifacts/dependency-audit-p004.json`：
51 个环境条目、50 个公告查询、本地项目跳过，0 条已知漏洞。
新增迁移变更必须继续覆盖原子提交、恢复备份、含数据降级拒绝和未知 schema 拒绝。
