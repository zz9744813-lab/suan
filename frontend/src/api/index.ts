// Domain-specific API helpers, all returning typed promises.

import { api } from "./client";
import type {
  AgentEvent,
  AgentStep,
  AgentTask,
  BehaviorPattern,
  Bible,
  Chapter,
  ChapterVersion,
  ChiefAgentMessage,
  ChiefAgentSession,
  DiscussionParticipantKey,
  DiscussionSession,
  GraphEdge,
  GraphNode,
  MaterialiseSummary,
  MemoryCharacter,
  MemoryForeshadow,
  MemoryHardFact,
  ModelHealthCheckResult,
  ModelPreviewResult,
  ModelProvider,
  ModelProviderTestResult,
  ModelRoleAssignment,
  Outline,
  Project,
  PromptTemplate,
  PromptVersion,
  SearchResult,
  StudyBehaviorExtractRequest,
  StudyBehaviorExtractResponse,
  StudyBulkRequestBody,
  StudyBulkStart,
  StudyCharacter,
  StudyForeshadowSummary,
  StudyMaterial,
  StudyMaterialDetail,
  StudyMaterialOverview,
  StudyChapter,
  StudyRelationshipApplyRequest,
  StudyRelationshipApplyResponse,
  StudyRelationshipsResponse,
  StudyRelationshipEnrichRequest,
  StudyRelationshipEnrichResponse,
  TaskDiagnosis,
  WorkerPolicy,
  WorkerStatus,
} from "../types";

// ----- projects -----
export const listProjects = () => api.get<Project[]>("/api/projects");
export const getProject = (id: number) => api.get<Project>(`/api/projects/${id}`);
export const createProject = (body: Partial<Project>) =>
  api.post<Project>("/api/projects", body);
export const updateProject = (id: number, body: Partial<Project>) =>
  api.patch<Project>(`/api/projects/${id}`, body);
export const deleteProject = (id: number) =>
  api.delete<{ deleted: number }>(`/api/projects/${id}`);

// Round 2: bulk reorder endpoint used by the drag-and-drop ProjectNav.
// Body matches the backend ``ProjectReorderRequest`` schema.
export type ProjectReorderItem = {
  project_id: number;
  sort_order: number;
  category?: string | null;
  pinned?: boolean;
};
export const reorderProjects = (items: ProjectReorderItem[]) =>
  api.post<{ updated: number }>("/api/projects/reorder", { items });

// Round 2: convenience — fire-and-forget PATCH that just bumps the
// project's last_opened_at. Used by the ProjectNav so the chief
// panel can show recently-touched projects without a separate poll.
export const touchProject = (id: number) =>
  api.patch<Project>(`/api/projects/${id}`, { touch_last_opened: true });

// ----- bible / outlines / chapters -----
export const getBible = (projectId: number) =>
  api.get<Bible>(`/api/projects/${projectId}/bible`);
export const updateBible = (projectId: number, body: Partial<Bible>) =>
  api.put<Bible>(`/api/projects/${projectId}/bible`, body);

export const listOutlines = (projectId: number) =>
  api.get<Outline[]>(`/api/projects/${projectId}/outlines`);
export const createOutline = (projectId: number, body: Partial<Outline>) =>
  api.post<Outline>(`/api/projects/${projectId}/outlines`, body);
export const bulkCreateOutlines = (projectId: number, items: Partial<Outline>[]) =>
  api.post<Outline[]>(`/api/projects/${projectId}/outlines/bulk`, items);

export const listChapters = (
  projectId: number,
  params: { status?: string } = {}
) => {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  const s = q.toString();
  return api.get<Chapter[]>(`/api/projects/${projectId}/chapters${s ? `?${s}` : ""}`);
};
export const createChapter = (projectId: number, body: Partial<Chapter>) =>
  api.post<Chapter>(`/api/projects/${projectId}/chapters`, body);

export const getChapter = (chapterId: number) =>
  api.get<Chapter>(`/api/chapters/${chapterId}`);
export const listChapterVersions = (chapterId: number) =>
  api.get<ChapterVersion[]>(`/api/chapters/${chapterId}/versions`);
export const getLatestVersion = (chapterId: number, kind: string) =>
  api.get<ChapterVersion>(`/api/chapters/${chapterId}/versions/${kind}`);
export const listChapterSteps = (chapterId: number) =>
  api.get<any[]>(`/api/chapters/${chapterId}/steps`);

// ----- tasks / worker -----
export const listTasks = (params: {
  project_id?: number;
  chapter_id?: number;
  status?: string;
  limit?: number;
} = {}) => {
  const q = new URLSearchParams();
  if (params.project_id) q.set("project_id", String(params.project_id));
  if (params.chapter_id) q.set("chapter_id", String(params.chapter_id));
  if (params.status) q.set("status", params.status);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<AgentTask[]>(`/api/tasks${s ? `?${s}` : ""}`);
};
export const createTask = (body: Partial<AgentTask>) =>
  api.post<AgentTask>("/api/tasks", body);
export const getTask = (id: number) => api.get<AgentTask>(`/api/tasks/${id}`);
export const cancelTask = (id: number) =>
  api.post<AgentTask>(`/api/tasks/${id}/cancel`);
// Round 3 / P1-FUNC-2: configurable retry. Mode defaults to
// ``full``; ``from_failed_step`` requires ``from_step``.
export type RetryMode = "full" | "from_failed_step" | "critic_only" | "continue_with_fallback";
export const retryTask = (
  id: number,
  body: { mode?: RetryMode; from_step?: string; reuse_previous_outputs?: boolean } = {},
) => api.post<AgentTask>(`/api/tasks/${id}/retry`, body);
export const taskSteps = (id: number) =>
  api.get<AgentStep[]>(`/api/tasks/${id}/steps`);
export const taskEvents = (id: number) =>
  api.get<AgentEvent[]>(`/api/tasks/${id}/events`);
// Round 3 / P1-FUNC-1: structured failure diagnosis (rail +
// suggestions + impact). Used by the dashboard's CurrentPipelinePanel
// and FailureDiagnosisCard.
export const getTaskDiagnosis = (id: number) =>
  api.get<TaskDiagnosis>(`/api/tasks/${id}/diagnosis`);

export const workerStatus = () => api.get<WorkerStatus>("/api/worker/status");
export const workerStart = () => api.post<any>("/api/worker/start");
export const workerPause = () => api.post<any>("/api/worker/pause");
export const workerResume = () => api.post<any>("/api/worker/resume");
export const workerStop = () => api.post<any>("/api/worker/stop");

export const getPolicy = (projectId: number) =>
  api.get<WorkerPolicy>(`/api/projects/${projectId}/policy`);
export const updatePolicy = (projectId: number, body: Partial<WorkerPolicy>) =>
  api.put<WorkerPolicy>(`/api/projects/${projectId}/policy`, body);
export const getDefaultPolicy = () =>
  api.get<WorkerPolicy>("/api/worker/policy");

// ----- prompts -----
export const listPromptTemplates = () =>
  api.get<PromptTemplate[]>("/api/prompts");
export const getPromptTemplate = (id: number) =>
  api.get<PromptTemplate>(`/api/prompts/${id}`);
export const listPromptVersions = (id: number) =>
  api.get<PromptVersion[]>(`/api/prompts/${id}/versions`);
export const createPromptVersion = (id: number, body: {
  body: string;
  activate?: boolean;
  change_note?: string;
}) => api.post<PromptVersion>(`/api/prompts/${id}/versions`, body);
export const activatePromptVersion = (templateId: number, versionId: number) =>
  api.post<PromptVersion>(`/api/prompts/${templateId}/versions/${versionId}/activate`);

// ----- model providers -----
export const listProviders = () => api.get<ModelProvider[]>("/api/models/providers");
export const getProvider = (id: number) =>
  api.get<ModelProvider>(`/api/models/providers/${id}`);
export const createProvider = (body: Partial<ModelProvider>) =>
  api.post<ModelProvider>("/api/models/providers", body);
export const updateProvider = (id: number, body: Partial<ModelProvider>) =>
  api.put<ModelProvider>(`/api/models/providers/${id}`, body);
export const deleteProvider = (id: number) =>
  api.delete<{ deleted: number }>(`/api/models/providers/${id}`);
export const testProvider = (id: number) =>
  api.post<ModelProviderTestResult>(`/api/models/providers/${id}/test`, undefined, 25_000);
// P0-MODEL-7: stateless model-list preview. Called from the new/edit
// Provider form so the user can pick ``default_model`` from a
// dropdown without first saving the row. Returns the list of model
// ids the provider exposes via /v1/models. 25s is plenty — the
// backend caps the read timeout at 15s for this call.
export const previewProviderModels = (baseUrl: string, apiKey: string) =>
  api.post<ModelPreviewResult>(
    "/api/models/providers/preview-models",
    { base_url: baseUrl, api_key: apiKey },
    25_000,
  );
// P0-MODEL-3: lightweight per-model health probe. The optional
// ``model`` query param targets a specific model id; omit it to test
// the provider's default model. The backend runs FOUR probes in
// sequence (the ``long_text`` probe can take ~30s on slow providers)
// so we give the frontend 120s headroom before the AbortController
// fires.
export const HEALTH_CHECK_TIMEOUT_MS = 120_000;
export const healthCheckProvider = (id: number, model?: string) =>
  api.post<ModelHealthCheckResult>(
    `/api/models/providers/${id}/health-check` + (model ? `?model=${encodeURIComponent(model)}` : ""),
    undefined,
    HEALTH_CHECK_TIMEOUT_MS,
  );

export const listRoles = () =>
  api.get<ModelRoleAssignment[]>("/api/models/roles");
export const setRole = (role: string, body: Partial<ModelRoleAssignment>) =>
  api.put<ModelRoleAssignment>(`/api/models/roles/${role}`, body);

// ----- chief agent -----
export const listChiefSessions = (projectId?: number) => {
  const q = projectId ? `?project_id=${projectId}` : "";
  return api.get<ChiefAgentSession[]>(`/api/chief-agent/sessions${q}`);
};
export const createChiefSession = (body: {
  title?: string;
  project_id?: number;
  page_context?: string;
}) => api.post<ChiefAgentSession>("/api/chief-agent/sessions", body);
export const listChiefMessages = (sessionId: number) =>
  api.get<ChiefAgentMessage[]>(`/api/chief-agent/sessions/${sessionId}/messages`);
export const chiefChat = (body: {
  session_id?: number;
  project_id?: number;
  page_context?: string;
  message: string;
}) => api.post<ChiefAgentMessage>("/api/chief-agent/chat", body);
export const confirmChiefAction = (actionId: string, body: any) =>
  api.post<any>(`/api/chief-agent/actions/${actionId}/confirm`, body);

// ----- Round 5: study (拆书) -----
export const listStudyMaterials = (projectId?: number) => {
  const q = projectId ? `?project_id=${projectId}` : "";
  return api.get<StudyMaterial[]>(`/api/study/materials${q}`);
};
export const createStudyMaterial = (body: {
  title: string;
  author?: string;
  source?: "paste" | "upload" | "url";
  project_id?: number;
  raw_text?: string;
}) => api.post<StudyMaterial>("/api/study/materials", body);
export const getStudyMaterial = (id: number, includeText = false) =>
  api.get<StudyMaterialDetail>(`/api/study/materials/${id}?include_text=${includeText ? 1 : 0}`);
export const updateStudyMaterial = (id: number, body: Partial<StudyMaterial>) =>
  api.patch<StudyMaterial>(`/api/study/materials/${id}`, body);
export const deleteStudyMaterial = (id: number) =>
  api.delete<{ deleted: number }>(`/api/study/materials/${id}`);
export const chapterizeStudyMaterial = (id: number, body: { min_chapter_chars?: number; pattern?: "auto" | "chinese" | "english" } = {}) =>
  api.post<StudyMaterialDetail>(`/api/study/materials/${id}/chapterize`, body);
export const listStudyChapters = (materialId: number) =>
  api.get<StudyChapter[]>(`/api/study/materials/${materialId}/chapters`);
export const listStudyCharacters = (materialId: number) =>
  api.get<StudyCharacter[]>(`/api/study/materials/${materialId}/characters`);
export const addStudyCharacter = (materialId: number, body: {
  name: string;
  aliases?: string[];
  role?: string;
  tags?: string[];
  base_profile?: Record<string, any> | null;
  confidence?: number;
}) => api.post<StudyCharacter>(`/api/study/materials/${materialId}/characters`, body);
export const deleteStudyCharacter = (materialId: number, characterId: number) =>
  api.delete<{ deleted: number }>(`/api/study/materials/${materialId}/characters/${characterId}`);
export const runStudyChapter = (materialId: number, body: { chapter_id: number; max_chars?: number }) =>
  api.post<StudyCharacter[]>(`/api/study/materials/${materialId}/study`, body);
// R21: bulk study — kicks off a background task and returns
// immediately with a ``task_id``. The caller polls
// ``GET /api/tasks/{task_id}`` to watch progress. Use
// ``mode='character'`` for the per-chapter character extraction
// (matches the "抽取人物" button), ``mode='event'`` for
// foreshadows (requires the book to be bound to a project), or
// ``mode='both'`` to run both in one pass.
export const runStudyBulk = (materialId: number, body: StudyBulkRequestBody = {}) =>
  api.post<StudyBulkStart>(`/api/study/materials/${materialId}/study/all`, body);
// Multipart upload (FormData). The client takes a Blob/File directly.
export const uploadStudyMaterial = (form: FormData) =>
  api.post<StudyMaterial>("/api/study/materials/upload", form);
// R19: batch upload — up to 5 books in a single multipart POST.
// Returns an array of per-file results: each entry is either
// `{ok: true, data: StudyMaterial}` or `{ok: false, error, filename}`.
// Backend auto-chapterizes each material by default.
export type BatchUploadResult = (
  | { ok: true; data: StudyMaterial; chapterize_error?: string }
  | { ok: false; filename?: string; error: string }
)[];
export const uploadStudyMaterialsBatch = (form: FormData) =>
  api.post<BatchUploadResult>("/api/study/materials/upload/batch", form);

// ----- R22: study → graph / behavior / foreshadow linkage -----

// Kick off an LLM run that turns a book into BehaviorPattern rows.
// ``body`` controls the cap on patterns and which chapters to use as
// evidence. Returns synchronously (one LLM call, no task_id).
export const extractStudyBehaviors = (materialId: number, body: StudyBehaviorExtractRequest = {}) =>
  api.post<StudyBehaviorExtractResponse>(
    `/api/study/materials/${materialId}/extract-behaviors`,
    body,
  );

// List the BehaviorPatterns sourced from this material (those with
// ``source_material_id = materialId``).
export const getStudyBehaviors = (materialId: number) =>
  api.get<BehaviorPattern[]>(`/api/study/materials/${materialId}/behaviors`);

// List the MemoryForeshadows stamped with this material id
// (``source_material_id = materialId``).
export const getStudyForeshadows = (materialId: number) =>
  api.get<StudyForeshadowSummary[]>(`/api/study/materials/${materialId}/foreshadows`);

// Co-occurrence analysis — for every character pair, count the
// chapters both of them appear in, and return the top N pairs.
export const getStudyRelationships = (materialId: number, params: { min_co_chapter_count?: number; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.min_co_chapter_count != null) q.set("min_co_chapter_count", String(params.min_co_chapter_count));
  if (params.limit != null) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<StudyRelationshipsResponse>(
    `/api/study/materials/${materialId}/relationships${s ? "?" + s : ""}`,
  );
};

// Persist the user-picked (pair, relation) tuples as GraphEdge rows
// under ``project_id``. Idempotent: same (source, target, relation)
// triple on the same project is skipped.
export const applyStudyRelationships = (materialId: number, body: StudyRelationshipApplyRequest) =>
  api.post<StudyRelationshipApplyResponse>(
    `/api/study/materials/${materialId}/relationships/apply`,
    body,
  );

// R24: upgrade the R22 "同章节出现" placeholder labels to real
// semantic relations (师父/对手/恋人/...) using a per-pair LLM
// call. ``body`` is optional; defaults to 30 pairs / co-occur ≥ 1.
export const enrichStudyRelationships = (materialId: number, body: StudyRelationshipEnrichRequest = {}) =>
  api.post<StudyRelationshipEnrichResponse>(
    `/api/study/materials/${materialId}/relationships/enrich`,
    body,
  );

// One-stop dashboard: chapter_count / character_count /
// behavior_count / foreshadow_count / graph_node_count, plus
// sample rows of each. The Study page uses this for the per-book
// 4-stat row so it doesn't have to make 4 round-trips.
export const getStudyMaterialOverview = (materialId: number) =>
  api.get<StudyMaterialOverview>(`/api/study/materials/${materialId}/overview`);

// ----- Round 5: behavior patterns -----
export const listBehaviorPatterns = (q: {
  character?: string[];
  situation?: string[];
  search?: string;
  source_material_id?: number;
  limit?: number;
} = {}) => {
  const params = new URLSearchParams();
  (q.character ?? []).forEach((c) => params.append("character", c));
  (q.situation ?? []).forEach((s) => params.append("situation", s));
  if (q.search) params.set("search", q.search);
  if (q.source_material_id != null) params.set("source_material_id", String(q.source_material_id));
  if (q.limit != null) params.set("limit", String(q.limit));
  const qs = params.toString();
  return api.get<BehaviorPattern[]>(`/api/behavior/patterns${qs ? "?" + qs : ""}`);
};
export const getBehaviorPattern = (id: number) =>
  api.get<BehaviorPattern>(`/api/behavior/patterns/${id}`);
export const createBehaviorPattern = (body: {
  name: string;
  character_tags?: string[];
  situation_tags?: string[];
  typical_behavior?: string[];
  dialogue_style?: string[];
  scene_function?: string[];
  risks?: string[];
  recommended_plot_followup?: string[];
  confidence?: number;
  evidence?: string[];
  source_material_id?: number;
}) => api.post<BehaviorPattern>("/api/behavior/patterns", body);
export const updateBehaviorPattern = (id: number, body: Partial<BehaviorPattern>) =>
  api.patch<BehaviorPattern>(`/api/behavior/patterns/${id}`, body);
export const deleteBehaviorPattern = (id: number) =>
  api.delete<{ deleted: number }>(`/api/behavior/patterns/${id}`);

// ----- Round E: Graph (人物关系图谱) -----
export const getGraph = (projectId: number) =>
  api.get<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/api/graph/${projectId}`);
export const createGraphNode = (projectId: number, body: {
  name: string;
  node_kind?: "study_character" | "project_character" | "faction" | "location" | "other";
  source_material_id?: number | null;
  ref_study_character_id?: number | null;
  ref_character_id?: number | null;
  extra?: Record<string, any> | null;
}) => api.post<GraphNode>(`/api/graph/${projectId}/nodes`, body);
export const updateGraphNode = (projectId: number, nodeId: number, body: Partial<GraphNode>) =>
  api.patch<GraphNode>(`/api/graph/${projectId}/nodes/${nodeId}`, body);
export const deleteGraphNode = (projectId: number, nodeId: number) =>
  api.delete<{ deleted: number }>(`/api/graph/${projectId}/nodes/${nodeId}`);
export const createGraphEdge = (projectId: number, body: {
  source_node_id: number;
  target_node_id: number;
  relation: string;
  weight?: number;
  evidence?: string | null;
}) => api.post<GraphEdge>(`/api/graph/${projectId}/edges`, body);
export const updateGraphEdge = (projectId: number, edgeId: number, body: Partial<GraphEdge>) =>
  api.patch<GraphEdge>(`/api/graph/${projectId}/edges/${edgeId}`, body);
export const deleteGraphEdge = (projectId: number, edgeId: number) =>
  api.delete<{ deleted: number }>(`/api/graph/${projectId}/edges/${edgeId}`);
export const materialiseFromStudy = (
  projectId: number,
  materialId: number,
  kind: "all" | "character" | "event" | "behavior" = "all",
  addCooccurrenceEdges: boolean = true,
) =>
  api.post<{ nodes: GraphNode[]; edges: GraphEdge[]; materialise_summary?: MaterialiseSummary }>(
    `/api/graph/${projectId}/materialise_from_study/${materialId}` +
      `?kind=${kind}&add_cooccurrence_edges=${addCooccurrenceEdges}`,
  );

// ----- Discussion Room -----
export const runDiscussion = (body: {
  project_id?: number;
  topic: string;
  participants: DiscussionParticipantKey[];
}) => api.post<DiscussionSession>("/api/discussion/run", body);

export const listDiscussionSessions = (projectId?: number) => {
  const q = projectId ? `?project_id=${projectId}` : "";
  return api.get<DiscussionSession[]>(`/api/discussion/sessions${q}`);
};

export const getDiscussionSession = (id: number) =>
  api.get<DiscussionSession>(`/api/discussion/sessions/${id}`);

// ----- Memory (Round 9) -----
export const listCharacters = (projectId: number) =>
  api.get<MemoryCharacter[]>(`/api/memory/projects/${projectId}/characters`);
export const createCharacter = (projectId: number, body: {
  name: string; aliases?: string[]; role?: string;
  tags?: string[]; base_profile?: Record<string, any>;
}) => api.post<MemoryCharacter>(`/api/memory/projects/${projectId}/characters`, body);
export const updateCharacter = (id: number, body: {
  name?: string; aliases?: string[]; role?: string;
  tags?: string[]; base_profile?: Record<string, any>;
}) => api.patch<MemoryCharacter>(`/api/memory/characters/${id}`, body);
export const deleteCharacter = (id: number) =>
  api.delete<{ deleted: number }>(`/api/memory/characters/${id}`);

export const listForeshadows = (projectId: number) =>
  api.get<MemoryForeshadow[]>(`/api/memory/projects/${projectId}/foreshadows`);
export const createForeshadow = (projectId: number, body: {
  name: string; summary?: string;
  planted_chapter?: number; expected_payoff_chapter?: number;
  importance?: number; related_characters?: string[];
  related_items?: string[]; related_main_plot?: string;
}) => api.post<MemoryForeshadow>(`/api/memory/projects/${projectId}/foreshadows`, body);
export const updateForeshadow = (id: number, body: {
  status?: "active" | "paid_off" | "dropped";
  actual_payoff_chapter?: number;
  importance?: number;
  name?: string; summary?: string;
  planted_chapter?: number; expected_payoff_chapter?: number;
  related_characters?: string[]; related_items?: string[];
  related_main_plot?: string;
}) => api.patch<MemoryForeshadow>(`/api/memory/foreshadows/${id}`, body);
export const deleteForeshadow = (id: number) =>
  api.delete<{ deleted: number }>(`/api/memory/foreshadows/${id}`);

export const listHardFacts = (projectId: number) =>
  api.get<MemoryHardFact[]>(`/api/memory/projects/${projectId}/hard-facts`);
export const createHardFact = (projectId: number, body: {
  category?: string; fact: string; source_chapter?: number;
}) => api.post<MemoryHardFact>(`/api/memory/projects/${projectId}/hard-facts`, body);
export const deleteHardFact = (id: number) =>
  api.delete<{ deleted: number }>(`/api/memory/hard-facts/${id}`);

// ----- Global Search (Round 11) -----
export const globalSearch = (q: string, limit = 30) => {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return api.get<SearchResult[]>(`/api/search?${params.toString()}`);
};

// ----- R25 / P2: DeepStudy (单书知识网络) -----
// 前端 helper. 后端端点 (R25 commit efeb960 加):
//   GET    /api/deepstudy/library                            书架列表
//   POST   /api/deepstudy/materials/{id}/runs                启动一次 run
//   GET    /api/deepstudy/runs/{id}                          run 进度
//   POST   /api/deepstudy/runs/{id}/{pause|resume|cancel}    状态机控制
//   GET    /api/deepstudy/materials/{id}/knowledge-graph     单书网络
//   GET    /api/deepstudy/materials/{id}/nodes/{node_id}     节点详情
//   GET    /api/deepstudy/patterns                           全局行为模式
//   GET    /api/deepstudy/techniques                         全局技巧库
//
// P2 范围: 书架入口 (StudyLibraryPage) + 单书网络 (StudyBookGraphPage)
// 都走这一组 helper; 启动 run 是 ShelfDetailPanel 的 "启动 DeepStudy" 按钮.

import type {
  LibraryResponse,
  StudyRunCreateBody,
  StudyRunRead,
  StudyRunStartResponse,
  KnowledgeGraphResponse,
  NodeDetailResponse,
} from "../types";

export const listDeepStudyLibrary = (params: { page?: number; page_size?: number; status?: string } = {}) => {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.status) q.set("status", params.status);
  const s = q.toString();
  return api.get<LibraryResponse>(`/api/deepstudy/library${s ? `?${s}` : ""}`);
};

export const startDeepStudyRun = (materialId: number, body: StudyRunCreateBody = {}) =>
  api.post<StudyRunStartResponse>(`/api/deepstudy/materials/${materialId}/runs`, body);

export const getDeepStudyRun = (runId: number) =>
  api.get<StudyRunRead>(`/api/deepstudy/runs/${runId}`);

export const pauseDeepStudyRun = (runId: number) =>
  api.post<StudyRunRead>(`/api/deepstudy/runs/${runId}/pause`);
export const resumeDeepStudyRun = (runId: number) =>
  api.post<StudyRunRead>(`/api/deepstudy/runs/${runId}/resume`);
export const cancelDeepStudyRun = (runId: number) =>
  api.post<StudyRunRead>(`/api/deepstudy/runs/${runId}/cancel`);

export const getKnowledgeGraph = (materialId: number) =>
  api.get<KnowledgeGraphResponse>(`/api/deepstudy/materials/${materialId}/knowledge-graph`);

/** 复合 ID 解析 — 前端按 ":" partition 拆 (entity:33 → entity / 33).
 *  后端路由直接接 node_id 字符串, 解析在 router 里做, 前端只负责 URL-encode. */
export const getDeepStudyNode = (materialId: number, nodeId: string) =>
  api.get<NodeDetailResponse>(`/api/deepstudy/materials/${materialId}/nodes/${encodeURIComponent(nodeId)}`);

export const listDeepStudyPatterns = (params: { q?: string; tag?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.q) q.set("q", params.q);
  if (params.tag) q.set("tag", params.tag);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<BehaviorPattern[]>(`/api/deepstudy/patterns${s ? `?${s}` : ""}`);
};

export const listDeepStudyTechniques = (params: { q?: string; technique_type?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.q) q.set("q", params.q);
  if (params.technique_type) q.set("technique_type", params.technique_type);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<any[]>(`/api/deepstudy/techniques${s ? `?${s}` : ""}`);
};
