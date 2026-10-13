export const modules = {
  tasks: {
    title: "任务总览",
    headline: "让一次调用，给出可核对的结果。",
    description: "运行固定合成场景，查看真实状态、事件与可校验报告。",
    unlock: "四种固定场景网页复现接入验收；任意工具与模型修复尚未开放",
    action: "查看运行记录",
    eyebrow: "任务与运行进度",
  },
  diagnosis: {
    title: "诊断分析",
    headline: "先验证假设，再决定改哪里。",
    description:
      "把已证实的问题与待验证的推测分开，每个判断都能追溯到对应的调用证据。",
    unlock: "P0-05 诊断角色接通后解锁",
    action: "预览诊断依据",
    eyebrow: "诊断能力与进度",
  },
  repairs: {
    title: "候选修复",
    headline: "每一处修改，都有清楚的理由。",
    description:
      "在隔离副本中生成候选补丁，对照影响范围和修改依据，再交给独立验证。",
    unlock: "P0-06 隔离补丁与验收门禁完成后解锁",
    action: "预览候选补丁",
    eyebrow: "修复能力与进度",
  },
  regression: {
    title: "回归验证",
    headline: "修好这个问题，也守住原有行为。",
    description: "对基线与候选使用同一套冻结的验收规则，让结果变化一目了然。",
    unlock: "P0-06 固定回归与基线比较完成后解锁",
    action: "预览回归对照",
    eyebrow: "验证能力与进度",
  },
  memory: {
    title: "项目记忆",
    headline: "把验证过的经验，留给下一次。",
    description: "记录项目约束、适用版本和确认来源；让已失效的经验退出决策。",
    unlock: "P1-02 项目经验存储接通后解锁",
    action: "预览经验条目",
    eyebrow: "项目记忆与进度",
  },
  connections: {
    title: "工具接入",
    headline: "连接工具，把观察变成真实证据。",
    description:
      "查看工具声明、协议与连接状态，将一次真实调用送入同一套检查流程。",
    unlock: "CLI 与公开复现已验证；受控 Docker CLI 已通过验收。任务总览接入四种固定场景；自定义工具接入仍待开发",
    action: "预览接入配置",
    eyebrow: "工具接入与进度",
  },
} as const;
export type ModuleKey = keyof typeof modules;
