/** 格式化工具。 */

/**
 * 主描述只看"预测的那件事"，剥掉历史数据里拼接的「（event_type）」尾巴。
 * 早期版本把 event_type 拼进 description（如「消息量激增（communication.message_volume_spike）」），
 * 而 event_type 又在卡片下方单独展示，导致重复。这里做兼容清洗。
 */
export const cleanDescription = (description: string, eventType?: string): string => {
  if (!description) return '';
  if (eventType) {
    const esc = eventType.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const stripped = description
      .replace(new RegExp(`[（(]\\s*${esc}\\s*[）)]\\s*$`), '')
      .trim();
    if (stripped) return stripped;
  }
  // 兜底：去掉末尾任意括号尾巴
  return description.replace(/[（(][^（）()]*[）)]\s*$/, '').trim() || description;
};

export const pct = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 3): string =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits);

export const shortDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('zh-CN');
};

export const shortDateTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', { hour12: false });
};

/** 概率 → 颜色。方案第 29.1 节首页要一眼看出高低。 */
export const probColor = (p: number): string => {
  if (p >= 0.7) return 'bg-jade-500';
  if (p >= 0.5) return 'bg-amber-500';
  return 'bg-sky-500';
};

/** 方案第 18 节：结果是 0 / 0.25 / 0.5 / 0.75 / 1.0 的刻度 */
export const outcomeLabel = (o: number): string => {
  switch (o) {
    case 1:
      return '完全发生';
    case 0.75:
      return '高度发生';
    case 0.5:
      return '部分发生';
    case 0.25:
      return '极弱发生';
    case 0:
      return '未发生';
    default:
      return `${(o * 100).toFixed(0)}%`;
  }
};

export const outcomeColor = (o: number): string => {
  if (o >= 0.75) return 'text-jade-400';
  if (o >= 0.5) return 'text-amber-400';
  if (o > 0) return 'text-orange-400';
  return 'text-cinnabar-400';
};

export const DOMAIN_LABEL: Record<string, string> = {
  career: '职业',
  money: '财务',
  study: '学习',
  social: '社交',
  relationship: '关系',
  travel: '出行',
  project: '项目',
  habit: '习惯',
  purchase: '消费',
  communication: '沟通',
  schedule: '日程',
  unexpected_event: '意外',
};

export const SCALE_LABEL: Record<string, string> = {
  day: '日',
  week: '周',
  month: '月',
  year: '年',
};

export const SOURCE_LABEL: Record<string, string> = {
  ziwei: '紫微',
  bazi: '八字',
  qimen: '奇门',
  liuyao: '六爻',
  meihua: '梅花',
  palm: '掌纹',
  face: '面相',
  reality: '现实',
  null: 'Null 基线',
};

export const STATUS_LABEL: Record<string, string> = {
  CANDIDATE: '候选',
  REJECTED: '已拦截',
  REWRITE: '待重写',
  EXPERIMENTAL: '实验性',
  FROZEN: '已冻结',
  VERIFY_REQUIRED: '待验证',
  WAITING_USER: '等待用户',
  VERIFIED: '已验证',
  EXPIRED_UNVERIFIED: '超期未验证',
  LEAKED: '结果泄漏',
};

/** 第 55 节数据来源分层 */
export const EVIDENCE_SOURCE_LABEL: Record<string, string> = {
  TRADITIONAL_RULE: '传统规则',
  CALENDAR: '历法',
  USER_REPORTED_REALITY: '用户上报',
  USER_PLAN: '用户计划',
  HISTORICAL_PATTERN: '历史规律',
  LLM_INFERENCE: 'LLM 推断',
  EXTERNAL_DATA: '外部数据',
};

export const RELIABILITY_LABEL: Record<string, string> = {
  low: '样本不足',
  medium: '中等',
  high: '可靠',
};

export const RELIABILITY_COLOR: Record<string, string> = {
  low: 'text-slate-500',
  medium: 'text-amber-400',
  high: 'text-jade-400',
};
