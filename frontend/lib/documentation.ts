export const documentationEntries = [
  { title: "安装与启动", slug: "getting-started", summary: "本地安装、服务启动和 CLI 使用。" },
  { title: "产品范围与约束", slug: "01-constraints", summary: "目标用户、支持范围和工程边界。" },
  { title: "架构与技术决策", slug: "02-architecture", summary: "组件边界、数据流和技术选型。" },
  { title: "P0 / P1 迭代计划", slug: "03-roadmap", summary: "任务依赖、当前进度与验收依据。" },
  { title: "Agent、工具与测试用例", slug: "17-agent-tools-testing-plan", summary: "角色职责、工具设计和逐项测试方案。" },
  { title: "Agent 契约验收记录", slug: "19-p0-05a-delivery", summary: "当前实现、实际测试与剩余工作。" },
  { title: "完整工程文档目录", slug: "index", summary: "全部规格、执行隔离、恢复与质量门禁。" },
];

export const documentationUrl = (slug: string) => `/docs/${slug.split("/").map(encodeURIComponent).join("/")}`;
