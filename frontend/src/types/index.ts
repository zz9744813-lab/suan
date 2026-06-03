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
  // P0-MODEL-3: per-model health probe state.
  last_health_status: ModelHealthStatus | null;
  last_health_message: string | null;
  last_health_latency_ms: number | null;
  last_health_model: string | null;
  last_health_at: string | null;
  // P15 / P0-HEALTH-1: per-test detail + role recommendations.
  // Single JSON blob so the role matrix can colour-code bindings
  // without re-running the probe on every page load.
  last_health_full: {
    results: ModelHealthCheckItem[];
    score: number;
    recommended_roles: Record<string, string>;
    checked_at: string;
  } | null;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

// P0-MODEL-3: friendly health enum the UI can render straight as a
// green / yellow / red pill. Keep these values in sync with the
// backend's ``HealthStatus`` Literal.
export type ModelHealthStatus =
  | "healthy"
  | "degraded"
  | "unreachable"
  | "auth_failed"
  | "model_missing"
  | "unknown_error";

export type ModelHealthItemName =
  | "short_chat"
  | "json_output"
  | "critic_schema"
  | "long_text";

export type ModelHealthItemStatus =
  | "passed"
  | "failed"
  | "warning"
  | "skipped";

// P15 / P0-HEALTH-1: per-test health item.
export type ModelHealthCheckItem = {
  name: ModelHealthItemName;
  status: ModelHealthItemStatus;
  latency_ms: number;
  message: string;
  suggestion?: string | null;
  raw_preview?: string | null;
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

// P0-MODEL-7: stateless model-list preview, used by the new/edit
// Provider form to populate the ``default_model`` dropdown without
// having to save the row first. Shape mirrors
// ``ProviderPreviewModelsResponse`` on the backend.
export type ModelPreviewResult = {
  ok: boolean;
  models: string[];
  message: string;
  suggestion?: string | null;
  latency_ms?: number | null;
};

// P0-MODEL-3 + P15 / P0-HEALTH-1: lightweight per-model health probe
// result. The top-level fields stay backward-compatible with the
// R11 ping-only probe; the per-test breakdown lives in ``results``.
export type ModelHealthCheckResult = {
  ok: boolean;
  status: ModelHealthStatus;
  message: string;
  suggestion?: string | null;
  model: string;
  latency_ms: number;
  checked_at: string;
  results: ModelHealthCheckItem[];
  score: number;
  // role -> "suitable" | "risky (slow: ...)" | "unsuitable (failed: ...)" | "unknown"
  recommended_roles: Record<string, string>;
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
  // P15 / P0-RETRY-1: ``reused`` joins the four existing terminal
  // states — it means "this step's output was carried over from a
  // previous run" (the user clicked "重试" with from_failed_step /
  // continue_with_fallback). The rail renders it as a calm blue
  // "↺ 复用" stop so the user can tell "ran" from "skipped but kept".
  status: string;          // succeeded / failed / pending / skipped / reused
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

// ----- Round 5: Study (拆书) / Behavior Pattern -----

export type StudyMaterial = {
  id: number;
  project_id: number | null;
  title: string;
  author: string;
  source: string;           // paste | upload | url
  status: string;           // empty | draft | ready | failed
  error: string | null;
  chapter_count: number;
  character_count: number;
  // Only populated on the detail view (and only if ``?include_text=1``
  // was sent). The list endpoint sends 0 to keep payloads small.
  raw_text_length: number;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

export type StudyMaterialDetail = StudyMaterial & {
  raw_text: string;
  chapters: StudyChapter[];
  characters: StudyCharacter[];
};

export type StudyChapter = {
  id: number;
  material_id: number;
  chapter_index: number;
  title: string;
  content: string;
  char_count: number;
  last_studied_at: string | null;
  created_at: string;
};

export type StudyCharacter = {
  id: number;
  material_id: number;
  source_chapter_id: number | null;
  name: string;
  aliases: string[];
  role: string;             // 主角|女主|男配|...|其他
  tags: string[];
  base_profile: Record<string, any> | null;
  confidence: number;       // 0..1
  created_at: string;
};

// R21: bulk study kick-off + live progress payloads. The
// `POST /api/study/materials/{id}/study/all` endpoint returns
// ``StudyBulkStart`` immediately; the caller polls
// ``GET /api/tasks/{task_id}`` and reads ``AgentTask.payload`` to
// see the per-chapter counters.
export type StudyBulkStart = {
  task_id: number;
  total_chapters: number;
  chapters_to_process: number;
  mode: "character" | "event" | "both";
  message?: string;
};

export type StudyBulkRequestBody = {
  mode?: "character" | "event" | "both";
  // 0 = no cap; otherwise process at most N chapters in this batch.
  limit?: number;
  // Up to 8 concurrent LLM calls. 3 is a sane default.
  max_concurrency?: number;
  // Re-extract chapters that already have last_studied_at.
  force?: boolean;
  // Per-chapter prompt cap, same semantics as runStudyChapter.
  max_chars?: number;
};

// R21: payload field on AgentTask for in-flight bulk study jobs.
export type StudyBulkPayload = {
  material_id: number;
  mode: "character" | "event" | "both";
  total_chapters: number;
  chapters_to_process: number;
  chapters_processed: number;
  characters_added: number;
  events_added: number;
  errors: string[];
  max_concurrency: number;
  force: boolean;
  max_chars: number;
};

export type BehaviorPattern = {
  id: number;
  source_material_id: number | null;
  name: string;
  character_tags: string[];
  situation_tags: string[];
  typical_behavior: string[];
  dialogue_style: string[];
  scene_function: string[];
  risks: string[];
  recommended_plot_followup: string[];
  confidence: number;
  evidence: string[];
  created_at: string;
  updated_at: string;
};

// ----- R22: study → graph / behavior / foreshadow linkage -----

// Response from ``POST /api/study/materials/{id}/extract-behaviors``.
// One LLM call, one or more BehaviorPattern rows persisted with
// source_material_id so the drafter pulls them by tag.
export type StudyBehaviorExtractRequest = {
  max_patterns?: number;
  force?: boolean;
  max_chunk_chars?: number;
  evidence_chapter_count?: number;
};

export type StudyBehaviorExtractResponse = {
  material_id: number;
  patterns_added: number;
  patterns_skipped: number;
  pattern_ids: number[];
  total_patterns_for_material: number;
  cost_usd: number;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  sample_names: string[];
};

// One suggested edge between two characters that co-occur in the
// same study chapter. The user picks a relation label at apply time
// (we don't try to infer "师父 vs 同门" from the chapter text).
export type StudyRelationshipSuggestion = {
  char_a_id: number;
  char_a_name: string;
  char_b_id: number;
  char_b_name: string;
  co_chapter_count: number;
  last_chapter_id: number;
  last_chapter_no: number;
  last_chapter_title: string;
  sample_quote: string;
};

export type StudyRelationshipsResponse = {
  material_id: number;
  chapters_scanned: number;
  suggestions: StudyRelationshipSuggestion[];
  total_characters: number;
  min_co_chapter_count: number;
};

export type StudyRelationshipApplyRequest = {
  project_id: number;
  // Each pair is { char_a_id, char_b_id, relation, weight?, evidence? }.
  pairs: Array<Record<string, any>>;
};

export type StudyRelationshipApplyResponse = {
  project_id: number;
  edges_added: number;
  edges_skipped: number;
  edge_ids: number[];
};

// One-stop dashboard for a study material. Aggregates the "where
// did the data go" question so the Study page can render a 4-stat
// row per book without four round-trips.
export type StudyMaterialOverview = {
  material_id: number;
  title: string;
  project_id: number | null;
  chapter_count: number;
  character_count: number;
  behavior_count: number;
  foreshadow_count: number;
  graph_node_count: number;
  sample_characters: Array<{
    id: number;
    name: string;
    role: string;
    tags: string[];
  }>;
  sample_behaviors: Array<{
    id: number;
    name: string;
    character_tags: string[];
    situation_tags: string[];
  }>;
  sample_foreshadows: Array<{
    id: number;
    name: string;
    summary: string;
    planted_chapter: number | null;
  }>;
};

// R22 materialise summary surfaced on the graph page. The route
// returns the standard GraphBundle in `data` plus this in a
// sibling field; the helper below mirrors that shape.
export type MaterialiseSummary = {
  nodes_created: number;
  edges_created: number;
};

// Memory-side foreshadow summary, returned by
// ``GET /api/study/materials/{id}/foreshadows``. Only the columns
// the Study page actually renders — fuller columns are available
// on the memory page.
export type StudyForeshadowSummary = {
  id: number;
  name: string;
  summary: string;
  planted_chapter: number | null;
  status: string;
  importance: number;
  related_characters: string[];
};

// ----- Round E: Graph (人物关系图谱) -----
// Nodes and edges are deliberately lightweight — the canvas in the
// Graph page is fully client-side, so the backend only persists the
// raw adjacency. Node/edge colours / layout / size are derived on
// the fly from ``node_kind`` and ``weight``.

export type GraphNodeKind =
  | "study_character"
  | "project_character"
  | "faction"
  | "location"
  | "other";

export type GraphNode = {
  id: number;
  project_id: number | null;
  source_material_id: number | null;
  node_kind: GraphNodeKind;
  name: string;
  ref_study_character_id: number | null;
  ref_character_id: number | null;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

export type GraphEdge = {
  id: number;
  project_id: number | null;
  source_node_id: number;
  target_node_id: number;
  relation: string;
  weight: number;
  evidence: string | null;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

// ===== Discussion Room (P0-FEAT-1) =====
export type DiscussionParticipantKey =
  | "planner" | "drafter" | "critic" | "continuity" | "memory";

export const DISCUSSION_PARTICIPANTS: { key: DiscussionParticipantKey; label: string; role: string; emoji: string }[] = [
  { key: "planner",    label: "策划",   role: "Planner",     emoji: "✎" },
  { key: "drafter",    label: "主笔",   role: "Drafter",     emoji: "✒" },
  { key: "critic",     label: "审稿",   role: "Critic",      emoji: "⚖" },
  { key: "continuity", label: "连戏",   role: "Continuity",  emoji: "🔗" },
  { key: "memory",     label: "记忆官", role: "Memory",      emoji: "📚" },
];

export type DiscussionTurn = {
  id: number;
  turn_no: number;
  agent_name: string;
  role_label: string;
  kind: "participant" | "synthesis";
  content: string;
  parsed: {
    key_points?: string[];
    concerns?: string[];
    summary?: string;
    agreement?: string[];
    tension?: string[];
    recommendation?: string;
    next_actions?: string[];
  } | null;
  error: string | null;
  duration_ms: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
};

export type DiscussionSession = {
  id: number;
  project_id: number | null;
  topic: string;
  participants: string[];
  status: "running" | "succeeded" | "failed" | "partial";
  error: string | null;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  created_at: string;
  turns: DiscussionTurn[];
};

// ===== Memory (Round 9) =====
export type MemoryCharacterState = {
  id: number;
  character_id: number;
  project_id: number;
  chapter_no: number;
  current_location: string | null;
  current_faction: string | null;
  current_goal: string | null;
  injury_state: string | null;
  emotion_state: string | null;
  secrets: string[];
  misunderstandings: string[];
  relationships: Record<string, any>;
  owned_items: string[];
  abilities: string[];
  last_seen_chapter: number | null;
};

export type MemoryCharacter = {
  id: number;
  project_id: number;
  name: string;
  aliases: string[];
  role: string;
  tags: string[];
  base_profile: Record<string, any>;
  latest_state: MemoryCharacterState | null;
};

export type MemoryForeshadow = {
  id: number;
  project_id: number;
  name: string;
  summary: string;
  planted_chapter: number | null;
  expected_payoff_chapter: number | null;
  actual_payoff_chapter: number | null;
  status: "active" | "paid_off" | "dropped";
  importance: number;
  related_characters: string[];
  related_items: string[];
  related_main_plot: string | null;
};

export type MemoryHardFact = {
  id: number;
  project_id: number;
  category: string;
  fact: string;
  source_chapter: number | null;
  created_at: string;
};

// ===== Global Search (Round 11, P0-UI-5) =====
export type SearchResultType =
  | "project"
  | "chapter"
  | "character"
  | "foreshadow"
  | "hard_fact"
  | "study_material"
  | "behavior_pattern";

export type SearchResult = {
  type: SearchResultType;
  id: number;
  title: string;
  snippet: string;
  link: string;
  score: number;
};
