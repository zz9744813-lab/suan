// Pydantic-style API envelope: { ok, data, error }
export type APIResponse<T> = {
  ok: boolean;
  data: T | null;
  error: { type: string; message: string; suggestion?: string; details?: any } | null;
};

export type Project = {
  id: number;
  name: string;
  genre: string;
  // Round 2: category is the grouping key the ProjectNav uses (falls
  // back to genre when null). sort_order orders within a group;
  // pinned floats the project above non-pinned peers. last_opened_at
  // powers the MRU badge in the chief panel.
  category: string | null;
  sort_order: number;
  pinned: boolean;
  last_opened_at: string | null;
  target_word_count: number;
  target_chapter_count: number;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  chapter_count: number;
  total_words: number;
};

export type Bible = {
  id: number;
  project_id: number;
  title: string;
  content: Record<string, any>;
  version: number;
  is_active: boolean;
  updated_at: string;
};

export type Outline = {
  id: number;
  project_id: number;
  volume_no: number;
  chapter_no: number;
  title: string;
  summary: string | null;
  importance: number;
  is_arc_peak: boolean;
  is_volume_climax: boolean;
  is_volume_opener: boolean;
  target_word_count: number;
  status: string;
};

export type Chapter = {
  id: number;
  project_id: number;
  outline_id: number | null;
  chapter_no: number;
  title: string;
  target_word_count: number;
  actual_word_count: number;
  status: string; // queued / drafting / in_review / done / needs_review
  current_score: number | null;
  updated_at: string;
};

export type ChapterVersion = {
  id: number;
  chapter_id: number;
  version_kind: string; // draft / rewrite_N / final
  version_no: number;
  content: string;
  summary: string | null;
  score: number | null;
  notes: Record<string, any> | null;
  created_at: string;
};

export type AgentTask = {
  id: number;
  project_id: number;
  chapter_id: number | null;
  task_type: string;
  status: string; // pending / running / succeeded / failed / cancelled
  priority: number;
  payload: Record<string, any>;
  error: string | null;
  retry_count: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at?: string;
};

export type AgentStep = {
  id: number;
  task_id: number;
  project_id: number;
  chapter_id: number | null;
  agent_name: string;
  step_name: string;
  status: string;
  input_prompt: string | null;
  raw_output: string | null;
  parsed_output: Record<string, any> | null;
  model_name: string | null;
  provider_name: string | null;
  prompt_template_id: number | null;
  prompt_version: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_ms: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type WorkerStatus = {
  state: string;
  current_task_id: number | null;
  last_heartbeat_at: string | null;
  consecutive_failures: number;
  today_words: number;
  today_cost_usd: number;
  last_error: string | null;
  is_loop_alive: boolean;
};

export type WorkerPolicy = {
  id: number;
  project_id: number;
  daily_word_goal: number;
  daily_budget_usd: number;
  pass_score: number;
  max_rewrite_rounds: number;
  max_retry_per_task: number;
  consecutive_fail_stop: number;
  auto_continue: boolean;
  discussion_policy: string;
  max_discussion_per_day: number;
  max_cost_per_discussion: number;
};

export type PromptTemplate = {
  id: number;
  template_key: string;
  name: string;
  category: string;
  role: string;
  scope: string;
  genre: string | null;
  description: string | null;
  allowed_inputs: string[];
  forbidden_inputs: string[];
  output_schema: string | null;
  can_modify: string[];
  cannot_modify: string[];
  hard_rules: string[];
  active_version_id: number | null;
  created_at: string;
  updated_at: string;
};

export type PromptVersion = {
  id: number;
  template_id: number;
  version: number;
  body: string;
  status: string; // active / candidate / deprecated
  change_note: string | null;
  test_pass_rate: number;
  avg_score_delta: number;
  usage_count: number;
  created_at: string;
};

export type ModelProvider = {
  id: number;
  name: string;
  base_url: string;
  // P0-6 fix: the backend never returns the full key. ``api_key`` is
  // a short masked preview (e.g. "sk-6…7dbe") and ``has_api_key`` is
  // the boolean the UI uses to decide whether to show the "已配置"
  // hint vs an empty input box.
  api_key: string;
  has_api_key: boolean;
  default_model: string;
  model_list: string[];
  enabled: boolean;
  last_test_status: string | null;
  last_test_message: string | null;
  last_test_at: string | null;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

export type ModelRoleAssignment = {
  id: number;
  role: string;
  provider_id: number;
  provider_name: string | null;
  model: string;
  temperature: number;
  max_tokens: number;
  notes: string | null;
};

export type ModelProviderTestResult = {
  ok: boolean;
  message: string;
  suggestion?: string;
  models: string[];
  latency_ms: number;
};

export type ChiefAgentMessage = {
  id: number;
  session_id: number;
  role: string; // user / chief
  content: string;
  actions: any[] | null;
  thinking: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  created_at: string;
};

export type ChiefAgentSession = {
  id: number;
  title: string;
  project_id: number | null;
  page_context: string | null;
  created_at: string;
};

export type AgentEvent = {
  id: number;
  project_id: number | null;
  chapter_id: number | null;
  task_id: number | null;
  event_type: string;
  level: string;
  message: string;
  data: Record<string, any> | null;
  created_at: string;
};

// Round 3 / P1-FUNC-1: structured task diagnosis. The backend
// flattens the chapter pipeline's AgentStep rows into a fixed 8-row
// rail (context_compile -> plan -> draft -> review -> rewrite ->
// continuity -> memory_update -> learning) and adds typed
// suggestions the UI can render as action buttons.
export type TaskDiagnosisStep = {
  step_name: string;
  label: string;
  status: string;          // succeeded / failed / pending / skipped
  agent_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  cost_usd: number;
  score: number | null;    // critic total, if any
  error_message: string | null;
};

export type TaskDiagnosisSuggestion = {
  type: "safe_retry" | "from_failed_step" | "continue_with_fallback"
      | "switch_model" | "view_step" | "open_models";
  label: string;
  description: string;
  risk: "low" | "medium" | "high";
  params: Record<string, any>;
};

export type TaskDiagnosis = {
  task_id: number;
  project_id: number;
  chapter_id: number | null;
  task_type: string;
  status: string;
  error_type: string;
  error_message: string;
  failed_agent: string | null;
  failed_step: string | null;
  impact: string[];
  suggestions: TaskDiagnosisSuggestion[];
  raw_output_preview: string | null;
  prompt_preview: string | null;
  steps: TaskDiagnosisStep[];
  retry_count: number;
};
