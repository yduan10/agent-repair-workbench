# Agent 模块组织与维护指南

2026-10-13 / 用户明确要求产品中不同 Agent 分目录。任务 DOC-02；架构约定先行，运行实现属于 P0-05 / P0-06。

## 1. 当前目录与目标结构

P0-05a已实现三个角色的`contracts.py`与`tests/`，以及公共类型/纯策略/只读接口目录。`agent.py`、提示词和实际模型循环仍待P0-05b；下方区分当前与目标结构。

```text
src/agent_workbench/
  agents/
    README.md
    diagnosis/
      README.md
      agent.py             # 角色行为（P0-05）
      contracts.py         # 已有 P0-05a：严格输出类型
      prompts/             # 版本化提示词（P0-05）
      tests/               # 已有 P0-05a：本角色契约单测
    repair/                # 相同组织方式；实际写入需 P0-06
    verification/          # 相同组织方式；独立程序验收不可由模型覆盖
  orchestration/           # 已有：共享类型/纯策略/catalog；实际状态图循环待b
  controlled_tools/        # 已有：五种请求schema；实际工具handler待b
  model_gateway/           # 后续：DeepSeek 适配、成本/预算、模型错误
  runner/                  # 已有 P0-03：唯一的进程/沙箱执行边界
  run_store/               # 已有 P0-04：事件、报告、lease 与显式恢复对账
  mcp_adapter.py           # 已有：真实 MCP 协议适配，与 Agent 角色分离
  checker.py               # 已有：确定性契约检查，与模型解释分离
```

公共输入值类型沿用当前 `models.py`，MCP 报告沿用 `mcp_models.py`，不为三个角色复制一套协议。仅一个角色使用的类型放在该角色 `contracts.py`；P0-05a跨角色协议经评审放在`orchestration/contracts.py`，与既有MCP原始证据类型分开。

## 2. 依赖与权限

- UI / API → 应用服务 → 编排器 → 角色显式入口；角色不互相导入 `agent.py`，不自行发起另一个角色的模型循环。
- 角色通过注入的模型接口和受控能力调用工具，不自行读取环境凭据、创建工具进程或绕过预算。
- 编排器负责运行状态、重试上限、时间/成本预算、权限检查和交接校验；不把这些规则藏在自然语言提示词中。
- 验证角色可以解释确定性结果，不能写入最终通过状态。验收器版本与测试集由应用冻结，模型只读。
- 角色 ID、角色版本与提示词版本由宿主审计封装附加，模型输出不可自填。P0-05a已冻结模型输出schema，运行审计封装在P0-05b落实，不先造无人使用的注册框架。
- 三个目录是首期职责边界，不是永久数量上限。增加角色必须有场景与对照证据，不能仅为增加 Agent 数量。

## 3. 新增一个角色的维护步骤

1. 在 `docs/02-architecture.md` 记录原因与替代方案，在台账创建任务、依赖和验收；说明为何现有角色无法覆盖。
2. 新建 `agents/<snake_case_role>/README.md`，写输入、输出、权限、预算、触发条件、停止条件和负责人。
3. 实现严格 `contracts.py`、单一入口 `agent.py`、版本化 `prompts/`；依赖从应用注入。
4. 在角色 `tests/` 覆盖正常、拒判、权限越界、注入、预算和模型失败；跨角色交接与回归放根目录 `tests/agents/`。
5. 到 P0-05 实现注册处后，再显式注册角色与允许的状态边。不得动态扫描目录自动执行代码，不允许用户上传内容注册可执行角色。
6. 运行同模型/同工具/同预算对照与全量固定回归，经独立代码审查后合入。
7. 同步网页能力状态、角色介绍与迭代历史。预览、开发中、CLI 可用、网页可用分别说明。

## 4. 测试发现与版本规则

P0-05a已将三个角色`tests/`加入pytest发现；同时扫描根 `tests/`、`experiments/public_mcp_case/test_prepare.py` 及 `containers/p0_03/test_prepare.py`。首次实现角色单元测试时，必须在同一改动将角色测试目录加入 pytest `testpaths` 并用 `pytest --collect-only` 核对，不得把测试放入角色目录却未进入 CI。

修改提示词也属于行为修改：附版本、固定回归与对照结果。跨角色契约破坏性修改需同步调用方与 schema 版本；禁止静默重解释旧运行记录。

具体角色输入/输出、工具权限与测试编号见 [17 实施规格](17-agent-tools-testing-plan.md)。角色目录 README 不能扩大宿主注册的工具权限；测试文件按 A/R 用例编号关联，不以目录存在作为功能完成依据。

## 5. 开发协作目录

ChatGPT 协作副本位于工作区 `agent-sandboxes/<task>/`，与产品 `agents/` 完全不同。每个副本负责指定文件，独立运行输出与测试；主 Agent 比较基线、检查差异后合入 `agent-workbench`。它们不进入产品分发、不能当作已实现的产品角色。当前仓库尚无首个提交，暂用独立副本，不为创建 worktree 擅自提交。
