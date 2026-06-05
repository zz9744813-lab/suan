import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ChapterDetail } from "./pages/ChapterDetail";
import { WorkerPage } from "./pages/WorkerPage";
import { TasksPage } from "./pages/TasksPage";
import { PromptsPage } from "./pages/PromptsPage";
import { ModelsPage } from "./pages/ModelsPage";
import { ModelConfigPage } from "./pages/ModelConfigPage";
import { ModelProviderDetailPage } from "./pages/ModelProviderDetailPage";
import { StudyLibraryPage, StudyBookGraphPage } from "./pages/StudyLibraryPage";
import { StudyPage } from "./pages/StudyPage";
import { DiscussionPage } from "./pages/DiscussionPage";
import { MemoryShelfPage, MemoryArchivePage } from "./pages/MemoryShelfPage";
import { AgentMemoryPage } from "./pages/AgentMemoryPage";
import { BehaviorPage } from "./pages/BehaviorPage";
import { GraphPage } from "./pages/GraphPage";
import { GraphsPage } from "./pages/GraphsPage";
import { GraphNetworkPage } from "./pages/GraphNetworkPage";
import { ReviewCommentsPage } from "./pages/ReviewCommentsPage";
import { ReaderAgentsPage } from "./pages/ReaderAgentsPage";
import { ReaderAgentDetailPage } from "./pages/ReaderAgentDetailPage";
import { AutomationAuditPage } from "./pages/AutomationAuditPage";
import { GenrePromptMatrixPage } from "./pages/GenrePromptMatrixPage";
import ModelObservabilityPanel from "./components/models/ModelObservabilityPanel";
import { AuditLogPage } from "./pages/AuditLogPage";
import { NotFound } from "./pages/NotFound";
import { useBackendHealth } from "./hooks/useBackendHealth";

// P0-MODEL-9: dev-mode banner so the operator can see at a glance
// whether the browser is talking to the backend directly (good) or
// still going through Vite's broken PUT-body proxy (bad). Shows
// only when ``import.meta.env.DEV`` is true. The banner is sticky at
// the top of every page so a misconfigured Vite is impossible to
// miss.
//
// R18: only the MISSING-CASE warning is rendered (red). The
// "everything is fine, VITE_API_BASE is set" green banner used to
// sit on every page, but it was constant noise once the
// ``.env.development`` shipped — operators already know they're in
// dev. Hide the happy-path entirely; show only the error.
function DevApiBaseBanner() {
  if (!import.meta.env.DEV) return null;
  const base = (import.meta.env.VITE_API_BASE as string) || "";
  if (base) return null; // healthy: API 直连, 无需提示
  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 9999,
        padding: "6px 12px",
        fontSize: 12,
        background: "rgba(220, 90, 90, 0.2)",
        borderBottom: "1px solid rgba(220, 90, 90, 0.5)",
        color: "#3a0a0a",
        textAlign: "center",
      }}
    >
      ⚠ dev 模式：<code>VITE_API_BASE</code> 未配置，API 走相对路径（Vite dev proxy），
      PUT/POST body 会被丢弃！请在 <code>frontend/.env.development</code> 里设置
      <code> VITE_API_BASE=http://127.0.0.1:8000 </code>并<strong>硬刷新浏览器</strong>。
    </div>
  );
}

// P3: Backend health banner — shows a sticky red bar when the backend is
// unreachable, so the user immediately knows *why* everything says
// "Failed to fetch" instead of debugging each page one by one.
function BackendHealthBanner() {
  const { ok, message } = useBackendHealth(15_000);
  if (ok) return null;
  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 9999,
        padding: "8px 16px",
        fontSize: 13,
        background: "rgba(220, 50, 50, 0.92)",
        color: "#fff",
        textAlign: "center",
        fontWeight: 600,
        letterSpacing: 0.3,
      }}
    >
      ⚠ 后端未连接 — {message || "请检查后端是否启动（dev.bat）"}
    </div>
  );
}

export default function App() {
  return (
    <AppShell>
      <DevApiBaseBanner />
      <BackendHealthBanner />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:pid" element={<ProjectPage />} />
        <Route path="/projects/:pid/chapters/:cid" element={<ChapterDetail />} />
        <Route path="/worker" element={<WorkerPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/models" element={<ModelConfigPage />} />
        <Route path="/models/providers/:providerId" element={<ModelProviderDetailPage />} />
        <Route path="/model-observability" element={<ModelObservabilityPanel projectId={undefined} />} />
        {/* P0 (01 §6) 路由基础规范: /study/library 是 P2 拆书书架
         * (主入口, 查书/启动 DeepStudy/看知识网络).
         * 旧 /study 重新挂上旧版 StudyPage, 给书架上的"📤 上传 /
         * 粘贴 / 行为模式"按钮当落地页. P2 commit 漏了这一步,
         * 旧路径被注释承诺"仍能直接打开", 实际把 /study 硬重定向
         * 到 /study/library 自己, 让按钮 click 看似无响应.
         * 这里改成渲染旧版 StudyPage, 书架 + 上传页各司其职. */}
        <Route path="/study" element={<StudyPage />} />
        <Route path="/study/library" element={<StudyLibraryPage />} />
        <Route path="/study/books/:materialId/graph" element={<StudyBookGraphPage />} />
        <Route path="/behavior" element={<BehaviorPage />} />
        <Route path="/graph" element={<Navigate to="/graphs" replace />} />
        <Route path="/graph/:projectId" element={<Navigate to="/graphs" replace />} />
        <Route path="/graphs" element={<GraphsPage />} />
        <Route path="/graphs/:materialId/network" element={<GraphNetworkPage />} />
        <Route path="/discussion" element={<DiscussionPage />} />
        {/* P10: Agent 分层记忆池 (三栏布局) */}
        <Route path="/memory" element={<AgentMemoryPage />} />
        {/* P3: 旧版记忆书架/档案馆保留 */}
        <Route path="/memory-shelf" element={<MemoryShelfPage />} />
        <Route path="/memory-shelf/:projectId" element={<MemoryArchivePage />} />
        {/* P6 P5: 评论区驱动的模拟读者 Agent 评审系统 (F:\07_P6 spec §7) */}
        <Route path="/reviews" element={<ReviewCommentsPage />} />
        {/* P7: Genre-Prompt matrix with drag-drop */}
        <Route path="/prompts-matrix" element={<GenrePromptMatrixPage />} />
        <Route path="/audit-logs" element={<AuditLogPage />} />
        {/* NF2: 读者Agent编辑中心 */}
        <Route path="/reader-agents" element={<ReaderAgentsPage />} />
        <Route path="/reader-agents/:readerKey" element={<ReaderAgentDetailPage />} />
        {/* NF2: 自动化审计 */}
        <Route path="/audit" element={<AutomationAuditPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  );
}
