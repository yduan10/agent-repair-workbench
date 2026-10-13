# 产品 Agent 模块

状态：P0-05a已实现三角色严格输出契约与单测；Agent运行逻辑仍待P0-05b，候选应用待P0-06。这些目录属于产品代码；与开发时的 ChatGPT 协作 Agent 无关。

- [diagnosis](diagnosis/README.md)：只读证据、提出可验证假设。
- [repair](repair/README.md)：提出局部候选补丁；实际编辑依赖隔离执行门禁。
- [verification](verification/README.md)：独立读取程序验收结果、解释是否满足固定标准。

每个角色的实现、契约、提示词和单元测试放在自己的目录。跨角色编排、模型调用、MCP 适配与运行状态不放入某个角色目录。完整边界与新增步骤见 [维护指南](../../../docs/09-agent-modules.md)。
