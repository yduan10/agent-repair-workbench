/** UI-03: release capabilities, reviewed against docs/03-roadmap.md.
 * This is development status, never live task data or a runtime health check.
 * Sidebar, module pages and homepage consume the same status definitions.
 */
export const capabilities = {
  checks: {
    label: "网页可用", tone: "available",
    completed: "证据导入、参数与结果契约检查、问题定位和报告下载已接通本地 API。",
    access: "直接在网页打开调用检查，导入自己的调用证据。",
    next: "任务总览已接入受控复现；模型分析从 CLI 发起，网页可读记录，审批仍在后续阶段。", milestone: "P0-01",
  },
  tasks: {
    label: "受控复现", tone: "available",
    completed: "运行记录与报告存储已完成；P1-01a 完成四种固定场景的网页发起、查询与停止请求，已通过真实容器验收与独立评审。",
    access: "在本机执行审核过的合成场景，查看真实状态及校验报告；不支持任意工具或代码。",
    next: "诊断页接入 CLI 分析记录；候选应用与审批仍待后续实现。", milestone: "P1-01a",
  },
  diagnosis: {
    label: "网页只读", tone: "available",
    completed: "CLI 三角色协作、五类受控工具和摘要存储已通过工程验收与独立代码复审；已有一次合成案例真实模型全流程记录。",
    access: "从 CLI 发起审核过的案例，在网页核对真实摘要、事件、预算与关联运行。",
    next: "P0-06 接入隔离候选应用与冻结回归。网页尚不发起模型分析。", milestone: "P0-05b",
  },
  repairs: {
    label: "待开发", tone: "planned",
    completed: "P0-03 已验证受控执行与资源限制，作为后续候选验证的基础。",
    access: "CLI 可生成临时片段建议，目前不应用补丁；下方仅展示候选审阅流程。",
    next: "P0-06 接入隔离补丁和冻结验收。", milestone: "P0-03",
  },
  regression: {
    label: "待开发", tone: "planned",
    completed: "执行与状态基础已有 344 项 Python 验收用例通过，其中包含 21 项真实容器验收。",
    access: "这是项目开发验收记录；尚不能在网页运行用户项目的基线与候选对比。",
    next: "P0-06 实现同一冻结测试集下的基线、候选比较与回归门禁。", milestone: "P0-03",
  },
  memory: {
    label: "待开发", tone: "planned",
    completed: "已确定角色目录与经验确认规则；项目记忆存储尚未实现。",
    access: "当前没有真实记忆条目，下方内容是交互示例。",
    next: "P1-02 实现经验存储、来源关联、版本匹配、失效与删除。", milestone: "DOC-02",
  },
  connections: {
    label: "CLI 可用", tone: "available",
    completed: "P0-02 · MCP CLI 已验证。P0-03 · 受控 Docker CLI 已验证。18 项真实容器验收及独立复审通过，覆盖故障注入、取消回收与宿主进程终止。",
    access: "可查看、下载下方协作接口目录，或在项目目录使用固定 CLI 配置。网页接入尚未开放；当前表单不会执行命令。",
    next: "任务总览接入四种固定合成场景；此页的自定义工具接入仍未开放。", milestone: "P0-03",
  },
} as const;
export type CapabilityKey = keyof typeof capabilities;
