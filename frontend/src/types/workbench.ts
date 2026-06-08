export type WorkbenchDomainKey = "writing" | "study" | "feedback" | "memory" | "governance";
export type WorkbenchDomainStatus = "healthy" | "warning" | "blocked" | "idle" | "running";
export type WorkbenchRiskSeverity = "info" | "warning" | "critical";
export type WorkbenchActionSeverity = "primary" | "normal" | "warning" | "danger";
export type WorkbenchTone = "neutral" | "ok" | "warning" | "danger";

export interface WorkbenchScope {
  mode: "global" | "project";
  project_id: number | null;
  project_name: string | null;
  domain: WorkbenchDomainKey | null;
}

export interface WorkbenchMetric {
  key: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  tone: WorkbenchTone;
}

export interface WorkbenchRisk {
  key: string;
  domain: WorkbenchDomainKey;
  severity: WorkbenchRiskSeverity;
  title: string;
  summary: string;
  entity_type: string | null;
  entity_id: number | null;
  project_id: number | null;
  chapter_id: number | null;
  task_id: number | null;
  route: string | null;
  created_at: string | null;
}

export interface WorkbenchAction {
  key: string;
  label: string;
  domain: WorkbenchDomainKey;
  severity: WorkbenchActionSeverity;
  requires_confirm: boolean;
  description: string | null;
  route: string | null;
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE" | null;
  endpoint: string | null;
  payload: Record<string, unknown>;
  disabled: boolean;
  disabled_reason: string | null;
}

export interface WorkbenchDomainCard {
  key: WorkbenchDomainKey;
  title: string;
  status: WorkbenchDomainStatus;
  summary: string;
  metrics: WorkbenchMetric[];
  risks: WorkbenchRisk[];
  actions: WorkbenchAction[];
  route: string;
}

export interface WorkbenchPrimaryTask {
  id: number | null;
  domain: WorkbenchDomainKey | null;
  title: string | null;
  task_type: string | null;
  task_kind: string | null;
  status: string | null;
  project_id: number | null;
  chapter_id: number | null;
  material_id: number | null;
  run_id: number | null;
  progress_current: number;
  progress_total: number;
  progress_percent: number | null;
  current_step: string | null;
  error: string | null;
  route: string | null;
  started_at: string | null;
}

export interface WorkbenchRecentOutput {
  key: string;
  domain: WorkbenchDomainKey;
  title: string;
  summary: string | null;
  entity_type: string;
  entity_id: number | null;
  project_id: number | null;
  chapter_id: number | null;
  route: string | null;
  created_at: string | null;
}

export interface WorkbenchWorkerSummary {
  state: string;
  loop_state: string | null;
  current_task_id: number | null;
  running_count: number;
  pending_count: number;
  failed_count: number;
  stale_running_tasks: number;
  last_heartbeat_at: string | null;
}

export interface WorkbenchModelSummary {
  providers_total: number;
  providers_healthy: number;
  providers_degraded: number;
  providers_failed: number;
  recent_failures: number;
  slow_calls: number;
  cost_today_usd: number;
}

export interface WorkbenchOverview {
  scope: WorkbenchScope;
  top_stats: WorkbenchMetric[];
  domains: WorkbenchDomainCard[];
  primary_task: WorkbenchPrimaryTask | null;
  risks: WorkbenchRisk[];
  recommended_actions: WorkbenchAction[];
  recent_outputs: WorkbenchRecentOutput[];
  worker: WorkbenchWorkerSummary;
  model_health: WorkbenchModelSummary;
  as_of: string;
}
