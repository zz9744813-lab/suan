// Domain-specific API helpers, all returning typed promises.

import { api } from "./client";
import type {
  AgentEvent,
  AgentStep,
  AgentTask,
  Bible,
  Chapter,
  ChapterVersion,
  ChiefAgentMessage,
  ChiefAgentSession,
  ModelProvider,
  ModelProviderTestResult,
  ModelRoleAssignment,
  Outline,
  Project,
  PromptTemplate,
  PromptVersion,
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
  api.post<ModelProviderTestResult>(`/api/models/providers/${id}/test`);

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
