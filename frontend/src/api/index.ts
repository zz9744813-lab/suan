// Domain-specific API helpers, all returning typed promises.

import { api, apiBase } from "./client";
import type {
  AgentEvent,
  AgentStep,
  AgentTask,
  APIResponse,
  BehaviorPattern,
  Bible,
  StudyBookDashboard,
  StudyShelf,
  Chapter,
  ChapterVersion,
  ChiefAgentMessage,
  ChiefAgentSession,
  DiscussionParticipantKey,
  DiscussionSession,
  GraphBundle,
  GraphDiagnosticsRead,
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
  // B3
  MultiWorkerStatus,
  // P7
  GenrePromptMapping,
  GenrePromptMatrixResponse,
  PromptSnapshotDetail,
  TemplateUsageRead,
  WorkbenchTopStats,
  WorkbenchLiveState,
  PromptCoverage,
  PromptUsageTop,
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

export type ProjectExportFormat = "markdown" | "txt" | "json" | "html";
function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (utf8) {
    try { return decodeURIComponent(utf8); } catch { return utf8; }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallback;
}
export async function exportProjectFile(projectId: number, format: ProjectExportFormat) {
  const url = `${apiBase}/api/projects/${projectId}/export?format=${encodeURIComponent(format)}`;
  const res = await fetch(url);
  if (!res.ok) {
    let message = `导出失败：HTTP ${res.status}`;
    try {
      const json = await res.json();
      message = json?.error?.message || json?.detail || message;
    } catch {
      // non-JSON export error, keep the HTTP summary
    }
    throw new Error(message);
  }
  return {
    blob: await res.blob(),
    filename: filenameFromDisposition(res.headers.get("Content-Disposition"), `project-${projectId}.${format === "markdown" ? "md" : format}`),
  };
}

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
  visibility?: string;
  domain?: string;
  task_kind?: string;
  parent_task_id?: number;
  limit?: number;
} = {}) => {
  const q = new URLSearchParams();
  if (params.project_id) q.set("project_id", String(params.project_id));
  if (params.chapter_id) q.set("chapter_id", String(params.chapter_id));
  if (params.status) q.set("status", params.status);
  if (params.visibility) q.set("visibility", params.visibility);
  if (params.domain) q.set("domain", params.domain);
  if (params.task_kind) q.set("task_kind", params.task_kind);
  if (params.parent_task_id) q.set("parent_task_id", String(params.parent_task_id));
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

// ===== P0 返工：Workbench 聚合 =====
export const getTopStats = () => api.get<WorkbenchTopStats>("/api/workbench/top-stats");
export const getLiveState = () => api.get<WorkbenchLiveState>("/api/workbench/live-state");

// ===== P0 返工 Phase 2.3+2.4: Prompt 覆盖率 / 使用追溯 =====
export const getPromptCoverage = () => api.get<PromptCoverage>("/api/prompts/coverage");
export const getPromptUsage = (templateId?: number, limit = 20) => {
  const params = templateId != null ? `?template_id=${templateId}&limit=${limit}` : `?limit=${limit}`;
  return api.get<PromptUsageTop>(`/api/prompts/usage${params}`);
};

export const workerStatus = () => api.get<WorkerStatus>("/api/worker/status");
export const multiWorkerStatus = () => api.get<MultiWorkerStatus>("/api/worker/multi-status");
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
  // P0 返工 Phase 3.1: 加 shelf_id (null=未分组)
  shelf_id?: number | null;
}) => api.post<StudyMaterial>("/api/study/materials", body);
export const getStudyMaterial = (id: number, includeText = false) =>
  api.get<StudyMaterialDetail>(`/api/study/materials/${id}?include_text=${includeText ? 1 : 0}`);
export const updateStudyMaterial = (id: number, body: Partial<StudyMaterial>) =>
  api.patch<StudyMaterial>(`/api/study/materials/${id}`, body);
// P0-拆书书架: 粘贴正文 + 自动分章 + 自动 DeepStudy
export const createStudyMaterialFromText = (body: {
  title: string;
  author?: string;
  raw_text: string;
  project_id?: number | null;
  shelf_category?: string | null;
  tags?: string[];
  auto_chapterize?: boolean;
  auto_deepstudy?: boolean;
  min_chapter_chars?: number;
}) => api.post<StudyMaterial>("/api/study/materials/from-text", body);

// P0-拆书书架: 深度删除 (含衍生产物清理)
export const deleteStudyMaterialDeep = (id: number, force = false) =>
  api.delete<{ material_id: number; title: string; deleted: Record<string, number> }>(
    `/api/study/materials/${id}${force ? "?force=true" : ""}`,
  );

// P0-拆书书架: 批量删除
export const batchDeleteStudyMaterials = (ids: number[], force = false) =>
  api.post<{
    deleted: Array<{ id: number; title?: string; deleted?: Record<string, number> }>;
    failed: Array<{ id: number; error: string }>;
  }>("/api/study/materials/batch-delete", { ids, force });

// P0-拆书书架: 图谱诊断
export const getDeepStudyDiagnostics = (materialId: number) =>
  api.get<{
    material_id: number;
    title: string;
    study_status: string;
    worker_state: string | null;
    latest_run: { id: number; status: string; current_stage: string | null; error: string | null } | null;
    counts: Record<string, number>;
    reason: string;
    message: string;
    suggested_action: string;
  }>(`/api/deepstudy/materials/${materialId}/diagnostics`);

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

// ----- P0 返工 Phase 3.2: 书架二层 API -----
// 列出所有书架 (含虚拟的 "未分组" 书架)
export const listStudyShelves = (projectId?: number) => {
  const params = new URLSearchParams();
  if (projectId != null) params.set("project_id", String(projectId));
  const q = params.toString();
  return api.get<APIResponse<StudyShelf[]>>(`/api/study/shelves${q ? `?${q}` : ""}`);
};

// 创建新书架
export const createStudyShelf = (body: {
  name: string;
  description?: string;
  project_id?: number;
  display_order?: number;
  color?: string;
}) => api.post<APIResponse<StudyShelf>>("/api/study/shelves", body);

// 改/删书架
export const updateStudyShelf = (id: number, body: Partial<{
  name: string;
  description: string;
  display_order: number;
  color: string | null;
}>) => api.patch<StudyShelf>(`/api/study/shelves/${id}`, body);

export const deleteStudyShelf = (id: number) =>
  api.delete<{ ok: boolean; data: { deleted: number } }>(`/api/study/shelves/${id}`);

// 第二层 — 列出某个书架上的书 (shelf_id=0 等于"未分组")
export const listStudyBooks = (shelfId?: number, projectId?: number) => {
  const params = new URLSearchParams();
  if (shelfId != null) params.set("shelf_id", String(shelfIdOrZero(shelfId)));
  if (projectId != null) params.set("project_id", String(projectId));
  const q = params.toString();
  return api.get<APIResponse<StudyMaterial[]>>(`/api/study/books${q ? `?${q}` : ""}`);
};

function shelfIdOrZero(id: number): number {
  // 0 = virtual "未分组" shelf, otherwise normal id
  return id;
}

// 单书 dashboard
export const getBookDashboard = (materialId: number) =>
  api.get<APIResponse<StudyBookDashboard>>(`/api/study/books/${materialId}/dashboard`);

// ----- Round 5: behavior patterns (B1 unified → behavior_cards) -----
export const listBehaviorPatterns = (q: {
  character?: string[];
  situation?: string[];
  search?: string;
  source_material_id?: number;
  source?: "all" | "cards" | "legacy";
  limit?: number;
} = {}) => {
  const params = new URLSearchParams();
  (q.character ?? []).forEach((c) => params.append("character", c));
  (q.situation ?? []).forEach((s) => params.append("situation", s));
  if (q.search) params.set("search", q.search);
  if (q.source_material_id != null) params.set("source_material_id", String(q.source_material_id));
  if (q.source) params.set("source", q.source);
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
// P0 返工 Phase 4.3: 图谱诊断 — 后端告诉你"图为什么是空的"
export const getGraphDiagnostics = (projectId: number) =>
  api.get<GraphDiagnosticsRead>(`/api/graph/${projectId}/diagnostics`);
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
// 都走这一组 helper; full run 由上传/入库流程自动创建，UI 只负责状态和失败修复.

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

// ----- P3: 项目记忆 (Raw + Stable + Discussion) -----
// 后端端点 (P3 spec 04 §10, 11 个):
//   GET    /api/project-memory                                          书架列表
//   GET    /api/project-memory/{project_id}                             档案馆概览
//   POST   /api/project-memory/{project_id}/consolidate                 二次加工
//   GET    /api/project-memory/{project_id}/entities?type=&search=      7 柜统一接口
//   GET    /api/project-memory/{project_id}/entities/{entity_id}        单实体详情
//   GET    /api/project-memory/{project_id}/foreshadows?status=         伏笔专用
//   GET    /api/project-memory/{project_id}/facts?category=             硬事实专用
//   GET    /api/project-memory/{project_id}/discussion-decisions        讨论裁决记录
//   POST   /api/project-memory/{project_id}/discussion-decisions/{id}/run  跑讨论
//   POST   /api/project-memory/{project_id}/discussion-decisions/{id}/apply 应用裁决
//   GET    /api/project-memory/{project_id}/raw-entries?status=         原始记忆池

import type {
  ApplyDecisionRequestBody,
  ApplyDecisionResponse,
  AgentModelBinding,
  AgentModelBindingUpdateBody,
  AgentPromptBinding,
  AgentPromptBindingUpdateBody,
  AgentRole,
  AgentRoleCreateBody,
  AgentRoleMatrixResponse,
  AgentRoleUpdateBody,
  AgentRun,
  AgentRunEvent,
  CabinetType,
  ConsolidateRequestBody,
  ConsolidateResponse,
  DiscussionDecision,
  ProjectMemoryArchiveOverview,
  ProjectMemoryShelfResponse,
  RawMemoryEntry,
  RunDiscussionRequestBody,
  StableMemoryEntity,
  StableMemoryEntityDetail,
} from "../types";

export const listProjectMemoryShelf = () =>
  api.get<ProjectMemoryShelfResponse>("/api/project-memory");

export const getProjectMemoryArchive = (projectId: number) =>
  api.get<ProjectMemoryArchiveOverview>(`/api/project-memory/${projectId}`);

export const consolidateProjectMemory = (projectId: number, body: ConsolidateRequestBody = {}) =>
  api.post<ConsolidateResponse>(`/api/project-memory/${projectId}/consolidate`, body);

/** 7 柜统一接口. type 不传 = 全部 active 实体. */
export const listProjectMemoryEntities = (
  projectId: number,
  params: { type?: CabinetType; search?: string; limit?: number } = {},
) => {
  const q = new URLSearchParams();
  if (params.type) q.set("type", params.type);
  if (params.search) q.set("search", params.search);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<StableMemoryEntity[]>(`/api/project-memory/${projectId}/entities${s ? `?${s}` : ""}`);
};

export const getProjectMemoryEntity = (projectId: number, entityId: number) =>
  api.get<StableMemoryEntityDetail>(`/api/project-memory/${projectId}/entities/${entityId}`);

/** 伏笔专用 — 走 status 过滤 (active/paid_off/dropped). */
export const listProjectMemoryForeshadows = (projectId: number, params: { status?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<StableMemoryEntity[]>(`/api/project-memory/${projectId}/foreshadows${s ? `?${s}` : ""}`);
};

/** 硬事实专用 — 走 tags 子串匹配 (P3 阶段没专门 category 列). */
export const listProjectMemoryFacts = (projectId: number, params: { category?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.category) q.set("category", params.category);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<StableMemoryEntity[]>(`/api/project-memory/${projectId}/facts${s ? `?${s}` : ""}`);
};

export const listDiscussionDecisions = (
  projectId: number,
  params: { status?: string; topic_type?: string; limit?: number } = {},
) => {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.topic_type) q.set("topic_type", params.topic_type);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<DiscussionDecision[]>(`/api/project-memory/${projectId}/discussion-decisions${s ? `?${s}` : ""}`);
};

export const runDiscussionDecision = (projectId: number, decisionId: number, body: RunDiscussionRequestBody = {}) =>
  api.post<DiscussionDecision>(`/api/project-memory/${projectId}/discussion-decisions/${decisionId}/run`, body);

export const applyDiscussionDecision = (projectId: number, decisionId: number, body: ApplyDecisionRequestBody = {}) =>
  api.post<ApplyDecisionResponse>(`/api/project-memory/${projectId}/discussion-decisions/${decisionId}/apply`, body);

export const listRawMemoryEntries = (
  projectId: number,
  params: { status?: string; limit?: number } = {},
) => {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.limit) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<RawMemoryEntry[]>(`/api/project-memory/${projectId}/raw-entries${s ? `?${s}` : ""}`);
};

// ----- P4: Agent Role / Model Binding / Prompt Binding / Run -----
// 后端端点 (P4 spec 05 §9, 12 个):
//   GET    /api/agent-roles                        角色列表
//   GET    /api/agent-roles/matrix                 角色矩阵 (核心)
//   POST   /api/agent-roles                        新增角色
//   GET    /api/agent-roles/{id}                   角色详情
//   PUT    /api/agent-roles/{id}                   更新角色
//   DELETE /api/agent-roles/{id}                   删除角色
//   PUT    /api/agent-roles/{id}/model-binding     改绑模型
//   PUT    /api/agent-roles/{id}/prompt-binding    改绑 prompt
//   GET    /api/agent-runs/current                 当前 runs
//   GET    /api/agent-runs?agent_role_id=          runs 历史
//   GET    /api/agent-runs/{id}                    单 run
//   GET    /api/agent-runs/{id}/events             run 事件流

export const listAgentRoles = (params: { category?: string; enabled_only?: boolean } = {}) => {
  const q = new URLSearchParams();
  if (params.category) q.set("category", params.category);
  if (params.enabled_only) q.set("enabled_only", "1");
  const s = q.toString();
  return api.get<AgentRole[]>(`/api/agent-roles${s ? `?${s}` : ""}`);
};

export const getAgentRoleMatrix = () =>
  api.get<AgentRoleMatrixResponse>("/api/agent-roles/matrix");

export const createAgentRole = (body: AgentRoleCreateBody) =>
  api.post<AgentRole>("/api/agent-roles", body);

export const getAgentRole = (id: number) =>
  api.get<AgentRole>(`/api/agent-roles/${id}`);

export const updateAgentRole = (id: number, body: AgentRoleUpdateBody) =>
  api.put<AgentRole>(`/api/agent-roles/${id}`, body);

export const deleteAgentRole = (id: number) =>
  api.delete<{ deleted: number }>(`/api/agent-roles/${id}`);

export const updateAgentModelBinding = (id: number, body: AgentModelBindingUpdateBody) =>
  api.put<AgentModelBinding>(`/api/agent-roles/${id}/model-binding`, body);

export const updateAgentPromptBinding = (id: number, body: AgentPromptBindingUpdateBody) =>
  api.put<AgentPromptBinding>(`/api/agent-roles/${id}/prompt-binding`, body);

export const listCurrentAgentRuns = () =>
  api.get<AgentRun[]>("/api/agent-runs/current");

export const listAgentRuns = (params: { agent_role_id?: number; project_id?: number; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (params.agent_role_id != null) q.set("agent_role_id", String(params.agent_role_id));
  if (params.project_id != null) q.set("project_id", String(params.project_id));
  if (params.limit != null) q.set("limit", String(params.limit));
  const s = q.toString();
  return api.get<AgentRun[]>(`/api/agent-runs${s ? `?${s}` : ""}`);
};

export const getAgentRun = (id: number) =>
  api.get<AgentRun>(`/api/agent-runs/${id}`);

export const getAgentRunEvents = (id: number, limit = 100) =>
  api.get<AgentRunEvent[]>(`/api/agent-runs/${id}/events?limit=${limit}`);

// ============================================================
// P7: Genre-Prompt mapping API
// ============================================================
export const getGenrePromptMatrix = () =>
  api.get<GenrePromptMatrixResponse>("/api/genre-prompts/matrix");

export const bindGenrePrompt = (data: { agent_role_key: string; genre: string; prompt_template_id: number; priority?: number }) =>
  api.put<GenrePromptMapping>("/api/genre-prompts/bind", data);

export const unbindGenrePrompt = (data: { agent_role_key: string; genre: string; prompt_template_id: number }) => {
  const q = new URLSearchParams({ agent_role_key: data.agent_role_key, genre: data.genre, prompt_template_id: String(data.prompt_template_id) });
  return api.delete<{ deleted: number }>(`/api/genre-prompts/unbind?${q.toString()}`);
};

export const reorderGenrePrompts = (items: { id: number; sort_order: number }[]) =>
  api.put<{ updated: number }>("/api/genre-prompts/reorder", { items });

export const getAvailableTemplates = (agent_role_key: string, genre?: string) => {
  const g = genre || "";
  return api.get<{ id: number; template_key: string; name: string; genre: string | null; category: string; role: string }[]>(
    `/api/genre-prompts/available?agent_role_key=${agent_role_key}&genre=${g}`
  );
};

export const getProjectPromptAudit = (projectId: number) =>
  api.get<PromptSnapshotDetail[]>(`/api/genre-prompts/projects/${projectId}/prompt-audit`);

export const getChapterPromptAudit = (projectId: number, chapterId: number) =>
  api.get<PromptSnapshotDetail>(`/api/genre-prompts/projects/${projectId}/chapters/${chapterId}/prompt-audit`);

export const createPromptTemplate = (data: {
  template_key: string; name: string; category?: string; role?: string;
  scope?: string; genre?: string | null; description?: string | null;
  initial_body?: string;
}) =>
  api.post<PromptTemplate>("/api/prompts/templates", data);

export const deletePromptTemplate = (id: number) =>
  api.delete<{ deleted: number }>(`/api/prompts/templates/${id}`);

export const getTemplateUsage = (id: number) =>
  api.get<TemplateUsageRead>(`/api/genre-prompts/templates/${id}/usage`);

// ---------------------------------------------------------------------------
// P8: Behavior Card knowledge base
// ---------------------------------------------------------------------------

export interface BehaviorCategoryRead {
  id: number; name: string; slug: string; description: string | null;
  icon: string | null; sort_order: number; is_collapsed: boolean;
  card_count: number; created_at: string; updated_at: string;
}

export interface CardTagRead { id: number; tag_type: string; tag_name: string; weight: number; }
export interface CardTechniqueRead { id: number; title: string; content: string; example: string | null; priority: number; }
export interface CardSourceRead { id: number; book_id: number | null; book_title: string | null; chapter_title: string | null; source_type: string; source_excerpt: string | null; extracted_summary: string | null; confidence: number; }
export interface CardUsageLogRead { id: number; project_id: number | null; chapter_id: number | null; task_id: number | null; agent_role: string | null; usage_type: string | null; prompt_excerpt: string | null; output_excerpt: string | null; feedback_score: number | null; created_at: string; }

export interface BehaviorCardSummary {
  id: number; category_id: number | null; name: string; role_type: string | null;
  status: string; avatar_symbol: string | null; color_theme: string | null;
  summary: string | null; behavior_chain: string | null; fit_score: number;
  source_count: number; technique_count: number; usage_count: number;
  sort_order: number; last_used_at: string | null; updated_at: string;
  tags: CardTagRead[];
}

export interface BehaviorCardDetail extends BehaviorCardSummary {
  typical_behavior: string | null; emotion_chain: string | null;
  dialogue_style: string | null; suitable_scenes: string | null;
  unsuitable_scenes: string | null; injection_hint: string | null;
  stability_score: number; dialogue_score: number; generalization_score: number;
  created_at: string; category: BehaviorCategoryRead | null;
  techniques: CardTechniqueRead[]; sources: CardSourceRead[];
  usage_logs: CardUsageLogRead[];
}

export interface BehaviorCardListResponse {
  items: BehaviorCardSummary[]; total: number;
}

export const listBehaviorCategories = () =>
  api.get<BehaviorCategoryRead[]>("/api/behavior-categories");

export const collapseBehaviorCategory = (id: number, is_collapsed: boolean) =>
  api.patch<BehaviorCategoryRead>(`/api/behavior-categories/${id}/collapse`, { is_collapsed });

export const listBehaviorCards = (q?: {
  keyword?: string; category_id?: number; role_tags?: string[];
  scene_tags?: string[]; status?: string; sort?: string;
  page?: number; page_size?: number;
}) => {
  const params = new URLSearchParams();
  if (q) {
    if (q.keyword) params.set("keyword", q.keyword);
    if (q.category_id != null) params.set("category_id", String(q.category_id));
    if (q.status) params.set("status", q.status);
    if (q.sort) params.set("sort", q.sort);
    if (q.page) params.set("page", String(q.page));
    if (q.page_size) params.set("page_size", String(q.page_size));
    q.role_tags?.forEach((t) => params.append("role_tags", t));
    q.scene_tags?.forEach((t) => params.append("scene_tags", t));
  }
  const qs = params.toString();
  return api.get<BehaviorCardListResponse>(`/api/behavior-cards${qs ? "?" + qs : ""}`);
};

export const getBehaviorCardDetail = (id: number) =>
  api.get<BehaviorCardDetail>(`/api/behavior-cards/${id}`);

export const createBehaviorCard = (body: Record<string, unknown>) =>
  api.post<BehaviorCardDetail>("/api/behavior-cards", body);

export const updateBehaviorCard = (id: number, body: Record<string, unknown>) =>
  api.put<BehaviorCardDetail>(`/api/behavior-cards/${id}`, body);

export const moveBehaviorCard = (id: number, target_category_id: number, sort_order?: number) =>
  api.patch<BehaviorCardSummary>(`/api/behavior-cards/${id}/move`, { target_category_id, sort_order });

export const archiveBehaviorCard = (id: number) =>
  api.post<{ id: number; status: string }>(`/api/behavior-cards/${id}/archive`);

// ---------------------------------------------------------------------------
// P9: Discussion Auto-Trace
// ---------------------------------------------------------------------------

export interface DiscussionStats {
  active_count: number; converged_count: number;
  pending_skill_count: number; recycle_soon_count: number; total_skill_count: number;
}
export interface ThreadSummary {
  id: number; project_id: number | null; chapter_id: number | null;
  title: string; summary: string | null;
  source_type: string; source_agent_role: string | null;
  issue_type: string; risk_level: string; status: string;
  requires_user_review: boolean; final_decision: string | null;
  recycle_at: string; recycled_at: string | null;
  rewrite_task_id: number | null; skill_draft_id: number | null;
  issue_fingerprint: string | null;
  created_at: string; updated_at: string;
  message_count: number; has_rewrite_task: boolean; has_skill_draft: boolean;
  remaining_seconds: number | null;
}
export interface ThreadListResponse { items: ThreadSummary[]; total: number; }
export interface IssueSourceRead {
  id: number; thread_id: number; source_type: string; source_id: number | null;
  chapter_id: number | null; chapter_index: number | null;
  quote: string | null; problem_summary: string; severity: string;
  payload_json: Record<string, unknown> | null; created_at: string;
}
export interface DiscussionMsgRead {
  id: number; thread_id: number; speaker_type: string; speaker_role: string;
  speaker_name: string | null; content: string;
  evidence_json: Record<string, unknown> | null; decision_tags_json: string[] | null;
  confidence: number | null; accepted_by_chief: boolean;
  provider_role: string | null; provider_name: string | null;
  model_name: string | null; error_message: string | null;
  token_in: number; token_out: number; cost_usd: number; created_at: string;
}
export interface SkillDraftRead {
  id: number; thread_id: number; project_id: number;
  title: string; skill_type: string; status: string;
  trigger_conditions_json: string[]; applicable_scenes_json: string[];
  anti_patterns_json: string[]; execution_template: string;
  prompt_snippet: string | null; applicable_agent_roles_json: string[];
  source_summary: string | null; source_thread_summary: string | null;
  quality_score: number; usage_count: number;
  created_at: string; solidified_at: string | null; solidified_skill_id: number | null;
}
export interface ThreadDetail extends ThreadSummary {
  task_id: number | null; final_reason: string | null;
  final_action_json: Record<string, unknown> | null;
  archive_payload_json: Record<string, unknown> | null;
  issue_sources: IssueSourceRead[]; messages: DiscussionMsgRead[];
  skill_draft: SkillDraftRead | null;
}
export interface SkillRead {
  id: number; title: string; skill_type: string;
  trigger_conditions_json: string[]; applicable_scenes_json: string[];
  anti_patterns_json: string[]; execution_template: string;
  prompt_snippet: string | null; applicable_agent_roles_json: string[];
  source_type: string; source_thread_id: number | null;
  quality_score: number; usage_count: number;
  created_at: string; updated_at: string;
}

export const listDiscussionThreads = (q?: {
  project_id?: number; status?: string; issue_type?: string;
  risk_level?: string; q?: string; page?: number; page_size?: number;
}) => {
  const params = new URLSearchParams();
  if (q) {
    if (q.project_id != null) params.set("project_id", String(q.project_id));
    if (q.status) params.set("status", q.status);
    if (q.issue_type) params.set("issue_type", q.issue_type);
    if (q.risk_level) params.set("risk_level", q.risk_level);
    if (q.q) params.set("q", q.q);
    if (q.page) params.set("page", String(q.page));
    if (q.page_size) params.set("page_size", String(q.page_size));
  }
  const qs = params.toString();
  return api.get<ThreadListResponse>(`/api/discussions${qs ? "?" + qs : ""}`);
};

export const getDiscussionStats = (project_id?: number) => {
  const p = project_id != null ? `?project_id=${project_id}` : "";
  return api.get<DiscussionStats>(`/api/discussions/stats${p}`);
};

export const getDiscussionThreadDetail = (id: number) =>
  api.get<ThreadDetail>(`/api/discussions/${id}`);

export const getDiscussionMessages = (id: number, page = 1, page_size = 50) =>
  api.get<DiscussionMsgRead[]>(`/api/discussions/${id}/messages?page=${page}&page_size=${page_size}`);

export const createDiscussionThread = (body: {
  project_id?: number; chapter_id?: number; title: string;
  issue_type?: string; risk_level?: string; user_note?: string;
}) => api.post<ThreadSummary>("/api/discussions", body);

export const runDiscussionThread = (id: number) =>
  api.post<ThreadSummary>(`/api/discussions/${id}/run`);

export const solidifySkill = (threadId: number, draftId: number, force = false) =>
  api.post<SkillRead>(`/api/discussions/${threadId}/solidify-skill`, { draft_id: draftId, force });

export const extendRecycle = (threadId: number, days: number, reason?: string) =>
  api.post<ThreadSummary>(`/api/discussions/${threadId}/extend-recycle`, { days, reason });

export const recycleNow = (threadId: number) =>
  api.post<ThreadSummary>(`/api/discussions/${threadId}/recycle-now`);

export const restoreThread = (threadId: number) =>
  api.post<ThreadSummary>(`/api/discussions/${threadId}/restore`);

// ============================================================
// P10: Agent Memory Layered Pool
// ============================================================

export interface AgentMemoryStats {
  agent_role: string;
  agent_name: string | null;
  memory_count: number;
  temporary_count: number;
  task_count: number;
  long_term_count: number;
  permanent_count: number;
  conflict_count: number;
  health_score: number;
  last_written_at: string | null;
  has_pending_audit: boolean;
}

export interface MemoryProjectStats {
  project_id: number;
  total: number;
  by_layer: Record<string, number>;
  by_agent: Record<string, number>;
  conflict_count: number;
  duplicate_candidate_count: number;
  health_score: number;
}

export interface MemoryEntryListItem {
  id: number;
  agent_role: string;
  visibility: string;
  memory_layer: string;
  memory_type: string;
  title: string;
  content_preview: string;
  tags: string[];
  confidence: number;
  importance: number;
  health_score: number;
  usage_count: number;
  last_used_at: string | null;
  is_locked: boolean;
  is_conflicted: boolean;
  is_duplicate_candidate: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryEntryDetail {
  id: number;
  project_id: number;
  agent_role: string;
  agent_name: string | null;
  visibility: string;
  memory_layer: string;
  memory_type: string;
  title: string;
  content: string;
  summary: string | null;
  tags: string[];
  chapter_id: number | null;
  task_id: number | null;
  discussion_thread_id: number | null;
  skill_id: number | null;
  source_type: string;
  source_id: string | null;
  source_quote: string | null;
  source_payload: Record<string, unknown> | null;
  confidence: number;
  importance: number;
  health_score: number;
  usage_count: number;
  last_used_at: string | null;
  ttl_seconds: number | null;
  expires_at: string | null;
  archived_at: string | null;
  deleted_at: string | null;
  is_locked: boolean;
  is_user_pinned: boolean;
  is_conflicted: boolean;
  is_duplicate_candidate: boolean;
  content_fingerprint: string | null;
  created_at: string;
  updated_at: string;
  links: MemoryLinkRead[];
  audit_logs: MemoryAuditLogRead[];
  recent_access_logs: MemoryAccessLogRead[];
}

export interface MemoryLinkRead {
  id: number;
  source_memory_id: number;
  target_memory_id: number;
  relation_type: string;
  description: string | null;
  confidence: number;
  created_by_agent_role: string | null;
  created_at: string;
}

export interface MemoryAuditLogRead {
  id: number;
  memory_id: number;
  project_id: number;
  action: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  actor_type: string;
  actor_role: string | null;
  reason: string | null;
  created_at: string;
}

export interface MemoryAccessLogRead {
  id: number;
  memory_id: number;
  project_id: number;
  agent_role: string;
  task_id: number | null;
  chapter_id: number | null;
  access_reason: string | null;
  injected_into_prompt: boolean;
  prompt_section: string | null;
  created_at: string;
}

export interface ChangeRequestRead {
  id: number;
  project_id: number;
  memory_id: number;
  request_type: string;
  requested_by_agent_role: string | null;
  reason: string;
  proposed_content: string | null;
  proposed_patch_json: Record<string, unknown> | null;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
}

export const getAgentMemoryStats = (projectId: number) =>
  api.get<MemoryProjectStats>(`/api/agent-memory/projects/${projectId}/stats`);

export const getAgentMemoryAgents = (projectId: number) =>
  api.get<{ items: AgentMemoryStats[] }>(`/api/agent-memory/projects/${projectId}/agents`);

export const listAgentMemoryEntries = (projectId: number, params?: Record<string, string | number | boolean | undefined>) => {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    }
  }
  const query = qs.toString();
  return api.get<{ items: MemoryEntryListItem[]; total: number }>(
    `/api/agent-memory/projects/${projectId}/entries${query ? "?" + query : ""}`,
  );
};

export const getAgentMemoryDetail = (memoryId: number) =>
  api.get<MemoryEntryDetail>(`/api/agent-memory/entries/${memoryId}`);

export const createAgentMemory = (projectId: number, body: Record<string, unknown>) =>
  api.post<MemoryEntryDetail>(`/api/agent-memory/projects/${projectId}/entries`, body);

export const updateAgentMemory = (memoryId: number, body: Record<string, unknown>) =>
  api.patch<MemoryEntryDetail>(`/api/agent-memory/entries/${memoryId}/update`, body);

export const promoteAgentMemory = (memoryId: number, body: { target_layer: string; reason: string; actor_type?: string }) =>
  api.post<MemoryEntryDetail>(`/api/agent-memory/entries/${memoryId}/promote`, body);

export const demoteAgentMemory = (memoryId: number, body: { target_layer: string; reason: string; actor_type?: string }) =>
  api.post<MemoryEntryDetail>(`/api/agent-memory/entries/${memoryId}/demote`, body);

export const archiveAgentMemory = (memoryId: number, body: { reason: string }) =>
  api.post<MemoryEntryDetail>(`/api/agent-memory/entries/${memoryId}/archive`, body);

export const mergeAgentMemories = (body: { source_ids: number[]; merged_title: string; merged_content: string; target_layer: string; reason: string }) =>
  api.post<MemoryEntryDetail>("/api/agent-memory/entries/merge", body);

export const markAgentMemoryConflict = (memoryId: number, body: { conflict_with_memory_id: number; reason: string }) =>
  api.post(`/api/agent-memory/entries/${memoryId}/mark-conflict`, body);

export const consolidateAgentMemory = (projectId: number, body: { agent_role?: string; job_types: string[] }) =>
  api.post(`/api/agent-memory/projects/${projectId}/consolidate`, body);

export const getAgentMemoryGraph = (projectId: number, agentRole?: string) => {
  const p = agentRole ? `?agent_role=${agentRole}` : "";
  return api.get<{ nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] }>(
    `/api/agent-memory/projects/${projectId}/graph${p}`,
  );
};

export const createChangeRequest = (body: { memory_id: number; request_type: string; reason: string; proposed_content?: string }) =>
  api.post<ChangeRequestRead>("/api/agent-memory/change-requests/", body);

export const reviewChangeRequest = (requestId: number, body: { status: string; review_note?: string }) =>
  api.post<ChangeRequestRead>(`/api/agent-memory/change-requests/${requestId}/review`, body);

// ── P4-Model-Failover: 新增 API ────────────────────────

export type ModelCandidateItem = {
  provider_id: number;
  provider_name: string;
  model_name: string;
  score: number;
  health?: number | null;
  success_rate?: number | null;
  latency_ms?: number | null;
  cost_score?: number | null;
  risk: string[];
};

export type PreviewSelectionResponse = {
  selected: ModelCandidateItem;
  candidates: ModelCandidateItem[];
};

export type AutoConfigureResponse = {
  updated: number;
  skipped_manual: number;
  failed: number;
  items: { agent_role_key: string; selection_mode: string; provider: string | null; model: string | null; score: number | null; reason: string | null }[];
};

export const previewModelSelection = (roleId: number, body: {
  selection_mode?: "auto" | "manual" | "manual_with_fallback";
  auto_strategy?: string;
  candidate_provider_ids?: number[];
  agent_role_key?: string;
}) =>
  api.post<PreviewSelectionResponse>(`/api/agent-roles/${roleId}/model-binding/preview-selection`, body);

export const autoConfigureAgents = (body: {
  project_id?: number;
  scope?: "all" | "auto_only";
  strategy?: string;
  overwrite_manual?: boolean;
  include_disabled?: boolean;
}) =>
  api.post<AutoConfigureResponse>("/api/agent-roles/auto-configure", body);

export const resetProviderCircuit = (providerId: number) =>
  api.post<{ ok: boolean; provider_id: number; circuit_state: string; message: string | null }>(
    `/api/models/providers/${providerId}/circuit/reset`, {},
  );

export const fullProviderHealth = (providerId: number) =>
  api.post<{
    provider_id: number; status: string; health_score: number; latency_ms: number | null;
    models: { model: string; available: boolean; json_score: number | null; long_output_score: number | null; speed_score: number | null; recommended_roles: string[] }[];
  }>(`/api/models/providers/${providerId}/health/full`, {});

// ----- model observability (S3) -----
export const getObservabilitySummary = () =>
  api.get<any>("/api/model-observability/summary");
export const getObservabilityEvents = (params?: { provider_id?: number; model_name?: string; limit?: number }) =>
  api.get<any>(`/api/model-observability/events?${new URLSearchParams(params as Record<string, string>)}`);
export const getObservabilityProviders = () =>
  api.get<any[]>("/api/model-observability/providers");
export const getRuntimeStats = (providerId: number, modelName: string) =>
  api.get<any>(`/api/model-observability/runtime-stats/${providerId}/${encodeURIComponent(modelName)}`);

// ----- audit logs (S5-T2) -----
export const listAuditLogs = (params?: { project_id?: number; event_type?: string; limit?: number; offset?: number }) =>
  api.get<any>(`/api/audit/logs?${new URLSearchParams(params as Record<string, string>)}`);

// ── Prompt Matrix Auto-Fill (NF2 阶段1) ──
export const previewPromptAutoFill = (body: { project_id?: number; scope?: string; strategy?: string; genres?: string[]; agent_role_keys?: string[] }) =>
  api.post<any>("/api/prompts/matrix/auto-fill/preview", body);

export const applyPromptAutoFill = (body: { batch_key: string; apply_confidence?: string[]; overwrite_locked?: boolean }) =>
  api.post<any>("/api/prompts/matrix/auto-fill/apply", body);

export const rollbackPromptAutoFill = (batchKey: string) =>
  api.post<any>(`/api/prompts/matrix/auto-fill/${batchKey}/rollback`, {});

export const getCellRecommendations = (agentRoleKey: string, genre: string) =>
  api.get<any>(`/api/prompts/matrix/cells/${agentRoleKey}/${encodeURIComponent(genre)}/recommendations`);

export const lockPromptCell = (agentRoleKey: string, genre: string) =>
  api.put<any>(`/api/prompts/matrix/cells/${agentRoleKey}/${encodeURIComponent(genre)}/lock`, {});

export const unlockPromptCell = (agentRoleKey: string, genre: string) =>
  api.put<any>(`/api/prompts/matrix/cells/${agentRoleKey}/${encodeURIComponent(genre)}/unlock`, {});

export const getPromptMatrixCoverage = (projectId?: number) =>
  api.get<any>(`/api/prompts/matrix/coverage${projectId ? `?project_id=${projectId}` : ""}`);

export const getTemplatePerformance = (templateId: number) =>
  api.get<any>(`/api/prompts/templates/${templateId}/performance`);

// ── Reader Agents (NF2 阶段3) ──
export const listReaderAgents = () =>
  api.get<any[]>("/api/reviews/readers");

export const getReaderAgent = (readerKey: string) =>
  api.get<any>(`/api/reviews/readers/${readerKey}`);

export const updateReaderAgent = (readerKey: string, body: Record<string, any>) =>
  api.patch<any>(`/api/reviews/readers/${readerKey}`, body);

export const getReaderComments = (readerKey: string, limit?: number) =>
  api.get<any[]>(`/api/reviews/readers/${readerKey}/comments${limit ? `?limit=${limit}` : ""}`);

export const getReaderStats = (readerKey: string) =>
  api.get<any>(`/api/reviews/readers/${readerKey}/stats`);

// ── Review Auto-Flow (NF2 阶段4) ──
export const getAutoFlowStatus = (projectId: number, chapterId?: number) => {
  const q = chapterId ? `?chapter_id=${chapterId}` : "";
  return api.get<any>(`/api/reviews/projects/${projectId}/auto-flow${q}`);
};

// ── Audit Events (NF2 阶段6) ──
export const getAuditStatsByEvent = (params?: { project_id?: number }) => {
  const q = new URLSearchParams();
  if (params?.project_id) q.set("project_id", String(params.project_id));
  return api.get<any>(`/api/audit/stats/by-event?${q.toString()}`);
};

// ----- Model Call Events (P0 Phase 8) -----
export const listModelCallEvents = (params?: { agent_role_key?: string; provider_id?: number; task_id?: number; limit?: number }) => {
  const q = new URLSearchParams();
  if (params?.agent_role_key) q.set("agent_role_key", params.agent_role_key);
  if (params?.provider_id != null) q.set("provider_id", String(params.provider_id));
  if (params?.task_id != null) q.set("task_id", String(params.task_id));
  if (params?.limit != null) q.set("limit", String(params.limit));
  return api.get<any[]>(`/api/model-observability/events?${q.toString()}`);
};

// ── P0 Observability Rework ──
export const getObservabilityModels = (params?: { hours?: number; provider_id?: number; agent_role_key?: string }) => {
  const q = new URLSearchParams();
  if (params?.hours) q.set("hours", String(params.hours));
  if (params?.provider_id) q.set("provider_id", String(params.provider_id));
  if (params?.agent_role_key) q.set("agent_role_key", params.agent_role_key);
  return api.get<any[]>(`/api/model-observability/models?${q.toString()}`);
};

export const getObservabilityAgents = (params?: { hours?: number; project_id?: number }) => {
  const q = new URLSearchParams();
  if (params?.hours) q.set("hours", String(params.hours));
  if (params?.project_id) q.set("project_id", String(params.project_id));
  return api.get<any[]>(`/api/model-observability/agents?${q.toString()}`);
};

export const getObservabilityFailures = (params?: { hours?: number; limit?: number }) => {
  const q = new URLSearchParams();
  if (params?.hours) q.set("hours", String(params.hours));
  if (params?.limit) q.set("limit", String(params.limit));
  return api.get<any[]>(`/api/model-observability/failures?${q.toString()}`);
};

export const getObservabilitySlowRequests = (params?: { hours?: number; threshold_ms?: number; limit?: number }) => {
  const q = new URLSearchParams();
  if (params?.hours) q.set("hours", String(params.hours));
  if (params?.threshold_ms) q.set("threshold_ms", String(params.threshold_ms));
  if (params?.limit) q.set("limit", String(params.limit));
  return api.get<any[]>(`/api/model-observability/slow-requests?${q.toString()}`);
};

// ----- NovelForge Knowledge Graph (单书知识网络 /graphs 路由) -----
export const listGraphBooks = (params: { status?: string } = {}) => {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  return api.get<any[]>(`/api/graphs/books${q.toString() ? '?' + q.toString() : ''}`);
};

export const getGraphNetwork = (materialId: number) =>
  api.get<any>(`/api/graphs/materials/${materialId}`);

export const getGraphNodeDetail = (materialId: number, nodeId: number) =>
  api.get<any>(`/api/graphs/materials/${materialId}/nodes/${nodeId}`);

export const getGraphEdgeDetail = (materialId: number, edgeId: number) =>
  api.get<any>(`/api/graphs/materials/${materialId}/edges/${edgeId}`);
