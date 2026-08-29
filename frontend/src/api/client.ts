/** 后端 API 客户端。 */

import type {
  Aggregate,
  EngineInfo,
  GateTestResponse,
  HistoryItem,
  OntologyItem,
  PredictionBrief,
  PredictionDetail,
  ReliabilityMatrix,
  RuleItem,
} from '../types';

const BASE = import.meta.env.VITE_BACKEND_URL ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail.slice(0, 300)}`);
  }
  return res.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });

// 演示用默认用户；完整实现应做登录与鉴权（第 64 节隐私）
export const DEFAULT_USER_ID = Number(import.meta.env.VITE_USER_ID ?? 1);

/** Calendar Core 快照（后端 /api/calendar/snapshot）。第 6 节。 */
export interface CalendarSnapshot {
  target_date: string;
  degraded: boolean;
  degrade_reason: string | null;
  payload: Record<string, unknown>;
}

export interface GenerateResult {
  target_date: string;
  scanned: number;
  candidate_count: number;
  frozen: {
    prediction_id: string;
    event_type: string;
    probability: number;
    null_probability: number | null;
    sha256: string;
    visibility: string;
  }[];
  rejected: { event_type: string; decision: string; failed: string[]; reasons: string[] }[];
  budget_usage: Record<string, number>;
  notes: string[];
}

export const api = {
  meta: () => get<Record<string, unknown>>('/'),
  health: () => get<{ status: string; engines: Record<string, { available: boolean }> }>('/health'),

  engines: () => get<{ engines: EngineInfo[]; available_count: number }>('/api/system/engines'),
  ontology: (domain?: string, scale?: string) =>
    get<{ count: number; items: OntologyItem[] }>(
      `/api/ontology${domain || scale ? `?${new URLSearchParams({ ...(domain ? { domain } : {}), ...(scale ? { scale } : {}) })}` : ''}`,
    ),
  rules: (status = 'active') =>
    get<{ count: number; items: RuleItem[] }>(`/api/rules?status=${status}`),

  generate: (userId: number, scale = 'day', limit = 20) =>
    post<GenerateResult>(`/api/predictions/generate?user_id=${userId}&scale=${scale}&limit=${limit}`),

  listPredictions: (userId: number, status?: string) =>
    get<{ count: number; items: PredictionBrief[] }>(
      `/api/predictions?user_id=${userId}${status ? `&status=${status}` : ''}`,
    ),

  duePredictions: (userId: number) =>
    get<{
      count: number;
      items: {
        prediction_id: string;
        event_type: string;
        description: string;
        probability: number;
        success_criteria: string[];
        failure_criteria: string[];
        window: [string, string];
        status: string;
      }[];
    }>(`/api/predictions/due?user_id=${userId}`),

  prediction: (id: string) => get<PredictionDetail>(`/api/predictions/${id}`),

  verify: (id: string, userReply?: string, quickAnswer?: string) => {
    const params = new URLSearchParams();
    if (userReply) params.set('user_reply', userReply);
    if (quickAnswer) params.set('quick_answer', quickAnswer);
    const qs = params.toString();
    return post<{
      prediction_id: string;
      outcome: number;
      confidence: number;
      needs_confirmation: boolean;
      disagreement: number;
      judges: { role: string; outcome: number; confidence: number }[];
      status: string;
    }>(`/api/predictions/${id}/verify${qs ? `?${qs}` : ''}`);
  },

  history: (userId: number) =>
    get<{ count: number; items: HistoryItem[] }>(`/api/predictions/history?user_id=${userId}`),

  overall: (userId?: number, domain?: string, timeScale?: string) => {
    const p = new URLSearchParams();
    if (userId) p.set('user_id', String(userId));
    if (domain) p.set('domain', domain);
    if (timeScale) p.set('time_scale', timeScale);
    return get<Aggregate>(`/api/analytics/overall?${p}`);
  },

  calibration: (userId?: number) =>
    get<{
      bins: { bin: string; n: number; predicted: number; actual: number; gap: number }[];
      overconfidence: number;
      sample_size: number;
      reliability: string;
    }>(`/api/analytics/calibration${userId ? `?user_id=${userId}` : ''}`),

  reliability: (userId?: number) =>
    get<ReliabilityMatrix>(`/api/analytics/reliability${userId ? `?user_id=${userId}` : ''}`),

  ablation: (userId?: number) =>
    get<{ runs: Record<string, unknown[]>; note: string }>(
      `/api/analytics/ablation${userId ? `?user_id=${userId}` : ''}`,
    ),

  futureTree: (userId: number, asOf?: string) =>
    get<{
      as_of: string;
      horizon_days: number;
      scenarios: { key: string; label: string; probability: number; description: string; evidence: string[] }[];
    }>(`/api/future-tree?user_id=${userId}${asOf ? `&as_of=${asOf}` : ''}`),

  counterfactual: (userId: number, interventions: { label: string; effects: Record<string, number> }[]) =>
    post<{
      as_of: string;
      scenarios: { key: string; label: string; dimensions: Record<string, number>; description: string }[];
    }>(`/api/counterfactual?user_id=${userId}`, { interventions }),

  gateTest: (payload: Record<string, unknown>) => post<GateTestResponse>('/api/adversarial/gate-test', payload),

  calendarSnapshot: (userId: number, targetDate?: string) =>
    get<CalendarSnapshot>(
      `/api/calendar/snapshot?user_id=${userId}${targetDate ? `&target_date=${targetDate}` : ''}`,
    ),

  createUser: (userKey: string, birth?: Record<string, unknown>) =>
    post<{ user_id: number; user_key: string }>('/api/users', {
      user_key: userKey,
      birth_profile: birth ?? null,
    }),

  listUsers: () => get<{ count: number; items: { id: number; user_key: string }[] }>('/api/users'),
};
