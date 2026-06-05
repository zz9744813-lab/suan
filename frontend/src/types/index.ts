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
  // P0 task center
  parent_task_id?: number | null;
  visibility?: string;
  domain?: string;
  task_kind?: string | null;
  material_id?: number | null;
  run_id?: number | null;
  stage_key?: string | null;
  progress_current?: number;
  progress_total?: number;
  display_title?: string | null;
  summary_json?: Record<string, any> | null;
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
  immutable: boolean;
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
  // P0-Model-Failover: Provider 级运行状态
  health_score: number;
  success_rate_1h: number;
  success_rate_24h: number;
  avg_latency_ms: number | null;
  consecutive_failures: number;
  consecutive_successes: number;
  circuit_state: "closed" | "open" | "half_open";
  circuit_open_until: string | null;
  last_failure_type: string | null;
  last_failure_message: string | null;
  last_success_at: string | null;
  daily_cost_usd: number;
  daily_request_count: number;
  daily_token_count: number;
  last_reset_date: string | null;
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

// R24: relationship LLM enrichment. The endpoint
// ``POST /api/study/materials/{id}/relationships/enrich`` runs
// one LLM call per co-occurrence pair to classify it into a
// semantic relation (师父/对手/恋人/...) instead of the default
// "同章节出现" co-occurrence label.
export type StudyRelationshipEnrichRequest = {
  // Reserved for future use — the backend currently re-uses the
  // R22 co-occurrence scanner. Pass empty list to mean "all
  // pairs above min_co_chapter_count".
  suggestion_ids?: number[];
  min_co_chapter_count?: number;
  max_pairs?: number;
};

export type StudyRelationshipEnrichedItem = {
  char_a_id: number;
  char_a_name: string;
  char_b_id: number;
  char_b_name: string;
  co_chapter_count: number;
  last_chapter_no: number;
  last_chapter_title: string;
  // Carried over from R22 — useful for tooltips / diff
  sample_quote: string;
  // New in R24: the LLM's verdict. ``llm_inferred=false`` means
  // the LLM returned "未知" / empty / failed; we fell back to
  // "同章节出现".
  relation: string;
  confidence: number;
  evidence: string;
  llm_inferred: boolean;
};

export type StudyRelationshipEnrichResponse = {
  material_id: number;
  enriched_count: number;
  skipped_count: number;
  fallback_count: number;
  duration_ms: number;
  cost_usd: number;
  items: StudyRelationshipEnrichedItem[];
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

// ===== R25: DeepStudy (单书知识网络 + 多 Agent 流水线) =====
// P2 范围: 拆书书架 (StudyLibraryPage) + 单书知识网络 (StudyBookGraphPage)
// 走这组 type, 数据源是 P0 (R25) commit efeb960 加的
// /api/deepstudy/* 端点 + 9 张表 (StudyRun/ChapterAnalysis/Entity/...).

/** Book spine row on the library shelf. 状态机:
 *  empty / uploaded / chapterized / studying / paused /
 *  review_required / completed / failed
 *  颜色映射见 P2 §2: completed=gold/blue / studying=purple /
 *  chapterized=green / failed=red / review_required=orange / uploaded=gray
 *  (orange 当前 P0 color token 表里没有, fallback red, P2.1 加) */
export type DeepStudyStatus =
  | "empty" | "uploaded" | "chapterized" | "studying"
  | "paused" | "review_required" | "completed" | "failed";

export type LibraryItem = {
  id: number;
  title: string;
  author: string;
  shelf_category: string | null;     // 用户分桶 (玄幻/都市/...)
  cover_theme: Record<string, any> | null;
  study_status: DeepStudyStatus;
  deepstudy_version: string | null;
  chapter_count: number;
  processed_chapters: number;
  entity_count: number;
  // 6 个深层 counter (R25 library 端点一次性 GROUP BY 出来, 避免 6 次往返)
  scene_beat_count: number;
  relationship_count: number;
  foreshadow_count: number;
  behavior_count: number;
  technique_count: number;
  knowledge_score: number | null;   // StudyCritic 给分
  last_deepstudied_at: string | null;
  cost_usd: number;
  project_id: number | null;
  created_at: string;
  updated_at: string;
};

export type LibrarySummary = {
  total_books: number;
  completed: number;
  studying: number;
  paused: number;
  review_required: number;
  failed: number;
  empty: number;
  chapterized: number;
  total_entities: number;
  total_relationships: number;
  total_techniques: number;
  total_cost_usd: number;
};

export type LibraryResponse = {
  items: LibraryItem[];
  summary: LibrarySummary;
  page: number;
  page_size: number;
  total: number;
};

export type StudyRunRead = {
  id: number;
  material_id: number;
  project_id: number | null;
  status: "queued" | "running" | "paused" | "succeeded" | "failed" | "cancelled";
  mode: "full" | "entities_only" | "relationships_only"
      | "behaviors_only" | "techniques_only" | "repair_failed";
  total_chapters: number;
  processed_chapters: number;
  current_stage: string | null;
  agent_plan: Record<string, any> | null;
  progress: Record<string, any> | null;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type StudyRunStartResponse = {
  run_id: number;
  material_id: number;
  status: StudyRunRead["status"];
  message: string;
};

export type StudyRunCreateBody = {
  mode?: StudyRunRead["mode"];
  chapter_range?: number[] | null;
  force?: boolean;
  max_concurrency?: number;
  model_roles?: Record<string, string> | null;
};

/** 单书知识网络 — 节点 id 是 "book:1" / "entity:33" / "scene:55" 形式的
 *  复合字符串, 跟 NodeDetailResponse 解析方式一致 (按 ":" partition). */
export type DeepStudyGraphNode = {
  id: string;
  type: string;
  label: string;
  size: number;
  score: number;
  chapter_index: number | null;
  extra: Record<string, any>;
};

export type DeepStudyGraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  weight: number;
  evidence: string | null;
  extra: Record<string, any>;
};

export type DeepStudyGraphStats = {
  nodes: number;
  edges: number;
  by_type: Record<string, number>;
};

export type KnowledgeGraphResponse = {
  book: Record<string, any>;
  nodes: DeepStudyGraphNode[];
  edges: DeepStudyGraphEdge[];
  stats: DeepStudyGraphStats;
};

export type NodeDetailResponse = {
  id: string;
  type: string;
  label: string;
  profile: Record<string, any>;
  mentions: Array<Record<string, any>>;
  relationships: Array<Record<string, any>>;
  scene_beats: Array<Record<string, any>>;
  foreshadows: Array<Record<string, any>>;
  behavior_patterns: Array<Record<string, any>>;
  techniques: Array<Record<string, any>>;
  agent_steps: Array<Record<string, any>>;
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

// ===== P3: 项目记忆库 (Raw + Stable + Discussion) =====
// 跟 backend/app/schemas/memory_v2.py 1:1 对应. 详情参见 P3 spec
// (04_P3_项目记忆书架_二次加工_讨论裁决.md) §7.

/** 第一层 — 项目记忆书架每一本记忆册. 7 柜 + 原始/裁决计数 + 健康分. */
export type ProjectMemoryShelfItem = {
  project_id: number;
  project_name: string;
  last_consolidated_at: string | null;
  // 7 档案柜 (P3 §5) — 跟 entity_type 一致
  character_count: number;
  location_count: number;
  faction_count: number;
  item_count: number;
  world_rule_count: number;
  foreshadow_count: number;
  hard_fact_count: number;
  // 原始 + 裁决计数 — 详情面板的"待裁决" badge
  raw_entry_count: number;
  raw_entry_pending: number;
  decision_pending: number;
  decision_running: number;
  // 0..1 — 健康分 (decided / 总裁决)
  health_score: number | null;
  // "active" / "archived"
  status: string;
};

/** 第一层 — 整个书架的响应, 含 3 本固定系统维护册 (P3 §4). */
export type ProjectMemoryShelfResponse = {
  items: ProjectMemoryShelfItem[];
  system_books: Array<{ key: string; label: string; subtitle: string }>;
};

/** 第二层 — 单项目档案馆概览 (7 柜 + 裁决室 + 健康). */
export type ProjectMemoryArchiveOverview = {
  project_id: number;
  project_name: string;
  health_score: number | null;
  last_consolidated_at: string | null;
  // 7 柜计数 (跟 ShelfItem 同结构但走 dict — 路由直接 GROUP BY 出来)
  counts: Record<string, number>;
  // pending / running / decided / failed 各自多少
  decision_summary: Record<string, number>;
};

// 7 柜的 entity_type 取值 (StableMemoryEntity.entity_type Literal)
export type CabinetType =
  | "character"
  | "location"
  | "faction"
  | "item"
  | "world_rule"
  | "foreshadow"
  | "hard_fact";

export const CABINETS: { key: CabinetType; label: string; emoji: string }[] = [
  { key: "character",   label: "人物档案",   emoji: "👤" },
  { key: "location",    label: "地点档案",   emoji: "🏔" },
  { key: "faction",     label: "势力档案",   emoji: "⚔" },
  { key: "item",        label: "物品档案",   emoji: "🗡" },
  { key: "world_rule",  label: "世界规则",   emoji: "📜" },
  { key: "foreshadow",  label: "伏笔档案",   emoji: "🎯" },
  { key: "hard_fact",   label: "硬事实",     emoji: "📌" },
];

/** P3 §7.1 原始记忆池. status 6 值:
 *  raw / processed / merged / rejected / needs_discussion / decided */
export type RawMemoryEntry = {
  id: number;
  project_id: number;
  chapter_id: number | null;
  chapter_index: number | null;
  entry_type: string;
  subject: string;
  predicate: string | null;
  object_value: string | null;
  raw_payload: Record<string, any>;
  source_quote: string | null;
  source_summary: string | null;
  confidence: number;
  agent_name: string;
  agent_step_id: number | null;
  status: string;
  processed_at: string | null;
  merged_into_entity_id: number | null;
  created_at: string;
};

/** P3 §7.2 稳定实体 (7 柜共用表). */
export type StableMemoryEntity = {
  id: number;
  project_id: number;
  entity_type: CabinetType;
  canonical_name: string;
  aliases: string[];
  tags: string[];
  profile: Record<string, any>;
  importance: number;
  confidence: number;
  status: string;
  first_chapter_index: number | null;
  last_chapter_index: number | null;
  created_at: string;
  updated_at: string;
};

/** P3 §7.3 人物当前状态. */
export type StableCharacterState = {
  id: number;
  project_id: number;
  entity_id: number;
  current_location: string | null;
  current_faction: string | null;
  current_goal: string | null;
  emotion_state: string | null;
  injury_state: string | null;
  power_state: string | null;
  owned_items: string[];
  abilities: string[];
  secrets: string[];
  last_seen_chapter: number | null;
  evidence_entry_ids: number[];
  confidence: number;
  updated_at: string;
};

/** P3 §7.4 时间线事件. */
export type MemoryTimelineEvent = {
  id: number;
  project_id: number;
  entity_id: number | null;
  memory_type: string;
  chapter_id: number | null;
  chapter_index: number | null;
  event_title: string;
  event_summary: string;
  before_state: Record<string, any> | null;
  after_state: Record<string, any> | null;
  source_quote: string | null;
  source_entry_id: number | null;
  created_by: string;
  created_at: string;
};

/** 单实体详情 — 基础 + latest_state + timeline. */
export type StableMemoryEntityDetail = StableMemoryEntity & {
  latest_state: StableCharacterState | null;
  timeline: MemoryTimelineEvent[];
};

/** P3 §7.5 讨论裁决记录.
 *  topic_type 5 值: duplicate_entity / field_conflict /
 *  foreshadow_unclear / hard_fact_conflict / relationship_conflict
 *  status 4 值: pending / running / decided / failed */
export type DiscussionDecision = {
  id: number;
  project_id: number;
  topic_type: string;
  topic_title: string;
  raw_entry_ids: number[];
  related_entity_ids: number[];
  status: string;
  decision_payload: Record<string, any> | null;
  decision: string | null;
  reason: string | null;
  decided_by_agent: string | null;
  discussion_session_id: number | null;
  created_at: string;
  decided_at: string | null;
};

export const DECISION_TOPIC_TYPE_LABEL: Record<string, string> = {
  duplicate_entity:    "实体去重",
  field_conflict:      "字段冲突",
  foreshadow_unclear:  "伏笔不清",
  hard_fact_conflict:  "硬事实冲突",
  relationship_conflict: "关系冲突",
};

export const DECISION_STATUS_LABEL: Record<string, string> = {
  pending:  "待裁决",
  running:  "裁决中",
  decided:  "已裁决",
  failed:   "裁决失败",
};

// ----- Consolidation / discussion 请求 / 响应 -----
export type ConsolidateRequestBody = {
  min_confidence?: number;
  batch_limit?: number;
  run_discussion_inline?: boolean;
};
export type ConsolidateResponse = {
  processed: number;
  merged: number;
  rejected: number;
  needs_discussion: number;
  decided_inline: number;
  decisions_created: number[];
  duration_ms: number;
  cost_usd: number;
};

export type RunDiscussionRequestBody = {
  participants?: string[];
  max_turns?: number;
};
export type ApplyDecisionRequestBody = {
  decision_payload_override?: Record<string, any> | null;
  reason_override?: string | null;
};
export type ApplyDecisionResponse = {
  decision_id: number;
  applied: boolean;
  affected_entity_ids: number[];
  created_timeline_event_ids: number[];
  message: string;
};

// ===== P4: Agent Role / Model Binding / Prompt Binding / Run / Event =====
// 跟 backend/app/schemas/agent_role.py 1:1 对应. P4 spec 05 §8/§9.
export type AgentCategory =
  | "writing" | "study" | "memory" | "discussion" | "custom";

export type AgentRunMode = "manual" | "pipeline" | "scheduled" | "event";

export type AgentStatus =
  | "idle" | "queued" | "running" | "waiting"
  | "succeeded" | "failed" | "disabled";

export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  idle:      "待命",
  queued:    "排队",
  running:   "运行中",
  waiting:   "等待上游",
  succeeded: "完成",
  failed:    "失败",
  disabled:  "禁用",
};

export const AGENT_CATEGORY_LABEL: Record<AgentCategory, string> = {
  writing:    "写作",
  study:      "拆书",
  memory:     "记忆",
  discussion: "讨论",
  custom:     "自定义",
};

// Avatar 样式 — 7 种内置 + 1 自定义
export type AgentAvatarStyle =
  | "orb" | "robot" | "scribe" | "critic" | "memory_core"
  | "study_core" | "discussion_core" | "custom";

export const AGENT_AVATAR_STYLES: { key: AgentAvatarStyle; label: string; emoji: string }[] = [
  { key: "orb",              label: "光球",      emoji: "●" },
  { key: "robot",            label: "机器人",    emoji: "⌬" },
  { key: "scribe",           label: "执笔",      emoji: "✎" },
  { key: "critic",           label: "天平",      emoji: "⚖" },
  { key: "memory_core",      label: "记忆核",    emoji: "❖" },
  { key: "study_core",       label: "研究核",    emoji: "☷" },
  { key: "discussion_core",  label: "讨论核",    emoji: "☕" },
  { key: "custom",           label: "自定义",    emoji: "✦" },
];

export type AgentRole = {
  id: number;
  key: string;
  display_name: string;
  description: string | null;
  category: AgentCategory;
  avatar_style: AgentAvatarStyle | null;
  enabled: boolean;
  visible_in_matrix: boolean;
  run_mode: AgentRunMode;
  pipeline_stage: string | null;
  timeout_seconds: number;
  max_retries: number;
  concurrency_limit: number;
  cost_limit_usd: number | null;
  created_at: string;
  updated_at: string;
};

export type AgentModelBinding = {
  id: number;
  agent_role_id: number;
  provider_id: number | null;
  model_name: string | null;
  fallback_provider_id: number | null;
  fallback_model_name: string | null;
  temperature: number | null;
  max_tokens: number | null;
  extra_body: Record<string, any> | null;
  // P0-Model-Failover 新增
  selection_mode: "auto" | "manual" | "manual_with_fallback";
  auto_strategy: "quality_first" | "cost_first" | "speed_first" | "long_context_first" | "json_stable_first";
  candidate_provider_ids: number[] | null;
  candidate_models_json: { provider_id: number; model: string; weight: number }[] | null;
  fallback_candidates_json: { provider_id: number; model: string; weight: number }[] | null;
  allow_auto_fallback: boolean;
  failure_threshold: number;
  cooldown_seconds: number;
  locked_reason: string | null;
  last_selected_provider_id: number | null;
  last_selected_model_name: string | null;
  last_selection_reason: string | null;
  last_selection_score: number | null;
  last_selection_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentPromptBinding = {
  id: number;
  agent_role_id: number;
  system_prompt_template_id: number | null;
  task_prompt_template_id: number | null;
  output_schema: Record<string, any> | null;
  strict_json: boolean;
  evidence_required: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: number;
  agent_role_id: number;
  project_id: number | null;
  task_id: number | null;
  agent_step_id: number | null;
  run_type: string;
  status: string;
  current_task: string | null;
  progress: number;
  provider_id: number | null;
  model_name: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  elapsed_ms: number | null;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type AgentRunEvent = {
  id: number;
  agent_run_id: number;
  event_type: string;
  message: string;
  payload: Record<string, any> | null;
  created_at: string;
};

/** 矩阵一行 — 角色 + 绑定 + 最新 run 状态 (P4 §9.4). */
export type AgentRoleMatrixItem = {
  role: AgentRole;
  binding: AgentModelBinding | null;
  prompt_binding: AgentPromptBinding | null;
  status: AgentStatus;
  status_label: string;
  current_task: string | null;
  progress: number;
  provider_name: string | null;
  model_name: string | null;
  last_run_id: number | null;
  last_run_at: string | null;
  last_error: string | null;
  total_runs: number;
  recent_runs: AgentRun[];
  recent_events: AgentRunEvent[];
};

export type AgentRoleMatrixResponse = {
  items: AgentRoleMatrixItem[];
  section_counts: Record<string, number>;
};

// ----- 创建 / 更新 Agent 表单 body -----
export type AgentRoleCreateBody = {
  key: string;
  display_name: string;
  description?: string | null;
  category: AgentCategory;
  avatar_style?: AgentAvatarStyle | null;
  enabled?: boolean;
  visible_in_matrix?: boolean;
  run_mode?: AgentRunMode;
  pipeline_stage?: string | null;
  timeout_seconds?: number;
  max_retries?: number;
  concurrency_limit?: number;
  cost_limit_usd?: number | null;
};

export type AgentRoleUpdateBody = Partial<Omit<AgentRoleCreateBody, "key">>;

export type AgentModelBindingUpdateBody = {
  provider_id?: number | null;
  model_name?: string | null;
  fallback_provider_id?: number | null;
  fallback_model_name?: string | null;
  temperature?: number | null;
  max_tokens?: number | null;
  extra_body?: Record<string, any> | null;
  // P0-Model-Failover 新增
  selection_mode?: "auto" | "manual" | "manual_with_fallback" | null;
  auto_strategy?: "quality_first" | "cost_first" | "speed_first" | "long_context_first" | "json_stable_first" | null;
  candidate_provider_ids?: number[] | null;
  candidate_models_json?: { provider_id: number; model: string; weight: number }[] | null;
  fallback_candidates_json?: { provider_id: number; model: string; weight: number }[] | null;
  allow_auto_fallback?: boolean | null;
  failure_threshold?: number | null;
  cooldown_seconds?: number | null;
  locked_reason?: string | null;
};

export type AgentPromptBindingUpdateBody = {
  system_prompt_template_id?: number | null;
  task_prompt_template_id?: number | null;
  output_schema?: Record<string, any> | null;
  strict_json?: boolean | null;
  evidence_required?: boolean | null;
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

// ===== P6: 评论区驱动的模拟读者 Agent 评审系统 =====

export type ReviewAuthorType = "user" | "reader_agent" | "chief_agent" | "system";
export type ReviewCommentStatus =
  | "new" | "replied" | "grouped" | "discussing"
  | "accepted" | "rejected" | "ignored" | "done";
export type ReviewSeverity = "low" | "medium" | "high" | "blocker";
export type ReviewGroupStatus =
  | "new" | "discussing" | "decided" | "rewrite_queued" | "done" | "ignored";

export type ReviewCommentRead = {
  id: number;
  project_id: number;
  chapter_id: number | null;
  chapter_version_id: number | null;
  parent_id: number | null;
  target_type: string;
  author_type: ReviewAuthorType;
  author_label: string;
  agent_role_id: number | null;
  content: string;
  evidence: Array<Record<string, any>> | null;
  rating: Record<string, any> | null;
  tags: string[];
  weight_at_created: number;
  status: ReviewCommentStatus;
  priority: number;
  related_group_id: number | null;
  related_discussion_id: number | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReviewCommentListResponse = {
  items: ReviewCommentRead[];
  total: number;
};

export type ReviewCommentGroupRead = {
  id: number;
  project_id: number;
  chapter_id: number | null;
  chapter_version_id: number | null;
  title: string;
  summary: string;
  comment_ids: number[];
  severity: ReviewSeverity;
  status: ReviewGroupStatus;
  discussion_session_id: number | null;
  decision: Record<string, any> | null;
  created_at: string;
  updated_at: string;
};

export type ReviewSettingsRead = {
  id: number;
  project_id: number;
  auto_reader_review: boolean;
  auto_chief_triage: boolean;
  auto_discussion: boolean;
  retention_days: number;
  max_comments_per_chapter: number;
  max_reader_comments_per_run: number;
  min_severity_for_discussion: ReviewSeverity;
  created_at: string;
  updated_at: string;
};

export type ReaderReviewRunRead = {
  id: number;
  project_id: number;
  chapter_id: number;
  chapter_version_id: number | null;
  trigger: string;
  status: string;
  reader_agent_keys: string[];
  generated_comment_ids: number[];
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

// P7: Genre-Prompt mapping types
export type GenrePromptMapping = {
  id: number;
  agent_role_key: string;
  genre: string;
  prompt_template_id: number;
  priority: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type MatrixCell = {
  agent_role_key: string;
  genre: string;
  prompt_template_id: number | null;
  template_key: string | null;
  template_name: string | null;
  priority: number;
  sort_order: number;
  state: "bound" | "fallback" | "empty";
};

export type GenrePromptMatrixResponse = {
  genres: string[];
  agent_role_keys: string[];
  cells: MatrixCell[];
};

export type PromptSnapshotDetail = {
  id: number;
  chapter_id: number | null;
  chapter_title: string | null;
  trigger: string;
  snapshot_data: Record<string, { template_key: string; template_id: number; version: number; genre: string }>;
  created_at: string;
};

export type TemplateUsageRead = {
  template_id: number;
  total_snapshots: number;
  chapter_ids: number[];
};
