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
  StudyCharacter,
  StudyMaterial,
  StudyMaterialDetail,
  StudyChapter,
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
// Multipart upload (FormData). The client takes a Blob/File directly.
export const uploadStudyMaterial = (form: FormData) =>
  api.post<StudyMaterial>("/api/study/materials/upload", form);

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
export const materialiseFromStudy = (projectId: number, materialId: number) =>
  api.post<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
    `/api/graph/${projectId}/materialise_from_study/${materialId}`,
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
