export type WorkbenchDomainKey = "writing" | "study" | "feedback" | "memory" | "governance";

export type DomainLink = {
  label: string;
  to: string;
  description: string;
  tone?: "primary" | "normal" | "warn";
};

export type DomainMetric = {
  label: string;
  value: string;
  hint: string;
};

export type DomainConfig = {
  key: WorkbenchDomainKey;
  label: string;
  shortLabel: string;
  navIcon: string;
  path: string;
  eyebrow: string;
  title: string;
  description: string;
  metrics: DomainMetric[];
  risks: string[];
  actions: string[];
  drilldowns: DomainLink[];
};

export const WORKBENCH_DOMAINS: DomainConfig[] = [
  {
    key: "writing",
    label: "创作生产",
    shortLabel: "创作",
    navIcon: "✍",
    path: "/workbench/writing",
    eyebrow: "Writing Pipeline",
    title: "创作生产线",
    description: "把项目、章节、任务和 Worker 状态收在一个入口里，专注推进正文生产。",
    metrics: [
      { label: "核心入口", value: "3", hint: "项目、任务、Worker" },
      { label: "产线状态", value: "实时", hint: "从旧页面下钻查看" },
      { label: "改造阶段", value: "M1", hint: "先收束导航，不重写业务" },
    ],
    risks: ["任务失败诊断仍在 Dashboard 和任务页查看", "章节级细节暂时保留在项目工作台"],
    actions: ["打开项目书架选择主写项目", "进入任务页查看队列", "检查 Worker 是否存活"],
    drilldowns: [
      { label: "项目书架", to: "/projects", description: "选择、创建、置顶和打开小说项目。", tone: "primary" },
      { label: "任务队列", to: "/tasks", description: "查看写作任务、失败原因和重试入口。" },
      { label: "Worker 控制台", to: "/worker", description: "查看生产线循环、当前任务和运行状态。" },
    ],
  },
  {
    key: "study",
    label: "素材研读",
    shortLabel: "研读",
    navIcon: "☷",
    path: "/workbench/study",
    eyebrow: "DeepStudy",
    title: "素材研读中心",
    description: "把拆书、图谱、行为模式和素材分析收束为写作前的知识加工区。",
    metrics: [
      { label: "核心入口", value: "4", hint: "书架、上传、图谱、行为" },
      { label: "知识流向", value: "记忆", hint: "分析结果沉淀到上下文" },
      { label: "改造阶段", value: "M1", hint: "先建立域首页" },
    ],
    risks: ["旧 /study 已跳转到 /study/library", "图谱仍保留独立网络页面"],
    actions: ["进入拆书书架导入素材", "查看图谱网络", "检查行为模式沉淀"],
    drilldowns: [
      { label: "拆书书架", to: "/study/library", description: "上传、分类、诊断和管理研读素材。", tone: "primary" },
      { label: "旧上传页", to: "/study/upload", description: "兼容旧拆书上传工作流。" },
      { label: "图谱中心", to: "/graphs", description: "查看素材图谱和实体关系网络。" },
      { label: "行为模式", to: "/behavior", description: "查看角色行为、技巧和模式分析。" },
    ],
  },
  {
    key: "feedback",
    label: "反馈闭环",
    shortLabel: "反馈",
    navIcon: "☕",
    path: "/workbench/feedback",
    eyebrow: "Reader Feedback",
    title: "反馈闭环中心",
    description: "把读者、评论评审、讨论室和改写决策放在同一条反馈链路里。",
    metrics: [
      { label: "核心入口", value: "3", hint: "评论、读者、讨论" },
      { label: "闭环目标", value: "裁决", hint: "从反馈到改写任务" },
      { label: "改造阶段", value: "M1", hint: "保留旧页面能力" },
    ],
    risks: ["读者 Agent 详情仍在旧编辑中心", "评论清理类内部任务不作为主标题展示"],
    actions: ["查看评论评审结果", "进入讨论室沉淀裁决", "维护模拟读者画像"],
    drilldowns: [
      { label: "评论评审", to: "/reviews", description: "查看模拟读者评论、评审和处理状态。", tone: "primary" },
      { label: "讨论室", to: "/discussion", description: "围绕反馈进行讨论、留痕和裁决。" },
      { label: "读者 Agent", to: "/reader-agents", description: "维护读者画像和评审角色。" },
    ],
  },
  {
    key: "memory",
    label: "记忆与知识",
    shortLabel: "知识",
    navIcon: "❖",
    path: "/workbench/memory",
    eyebrow: "Memory Layer",
    title: "记忆与知识中心",
    description: "集中查看 Agent 分层记忆、旧版记忆书架和项目知识沉淀入口。",
    metrics: [
      { label: "核心入口", value: "2", hint: "分层记忆、旧书架" },
      { label: "服务对象", value: "全域", hint: "创作、研读和反馈共享" },
      { label: "改造阶段", value: "M1", hint: "先作为知识入口" },
    ],
    risks: ["项目级记忆仍从项目详情下钻", "旧记忆书架保留用于兼容"],
    actions: ["打开 Agent 分层记忆池", "从项目页进入项目记忆", "需要时访问旧版记忆书架"],
    drilldowns: [
      { label: "Agent 记忆库", to: "/memory", description: "查看分层记忆池、变更和沉淀内容。", tone: "primary" },
      { label: "旧版记忆书架", to: "/memory-shelf", description: "兼容旧项目记忆册和档案馆。" },
      { label: "项目书架", to: "/projects", description: "从项目详情进入对应项目记忆。" },
    ],
  },
  {
    key: "governance",
    label: "模型与治理",
    shortLabel: "治理",
    navIcon: "⚖",
    path: "/workbench/governance",
    eyebrow: "Model Governance",
    title: "模型与治理中心",
    description: "收束模型配置、提示词矩阵、可观测性和自动化审计，作为系统治理入口。",
    metrics: [
      { label: "核心入口", value: "5", hint: "模型、提示词、审计" },
      { label: "治理对象", value: "质量", hint: "成本、稳定性、可观测" },
      { label: "改造阶段", value: "M1", hint: "先统一入口" },
    ],
    risks: ["模型健康数据后续由 overview 接入", "不要恢复 /audit-logs 双入口"],
    actions: ["检查模型 Provider 配置", "维护提示词与矩阵", "查看自动化审计"],
    drilldowns: [
      { label: "模型配置", to: "/models", description: "配置模型供应商、角色绑定和路由策略。", tone: "primary" },
      { label: "提示词配置", to: "/prompts", description: "维护系统提示词和版本。" },
      { label: "提示词矩阵", to: "/prompts-matrix", description: "按类型和场景管理提示词组合。" },
      { label: "可观测性", to: "/model-observability", description: "查看模型调用、成本和健康状态。" },
      { label: "自动化审计", to: "/audit", description: "查看审计记录和系统治理事件。", tone: "warn" },
    ],
  },
];

export const WORKBENCH_DOMAIN_BY_KEY = Object.fromEntries(
  WORKBENCH_DOMAINS.map((domain) => [domain.key, domain]),
) as Record<WorkbenchDomainKey, DomainConfig>;

export function getWorkbenchDomain(key: WorkbenchDomainKey): DomainConfig {
  return WORKBENCH_DOMAIN_BY_KEY[key];
}
