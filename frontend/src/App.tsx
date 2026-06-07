import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { lazy, Suspense } from "react";
import { AppShell } from "./components/AppShell";
import { PageSkeleton } from "./components/layout/PageSkeleton";
import { useBackendHealth } from "./hooks/useBackendHealth";

/* ------------------------------------------------------------------
   Route-level lazy loading.
   Named exports use .then(m => ({ default: m.X })) pattern.
   Default exports use the simpler lazy(() => import(...)) form.
   ------------------------------------------------------------------ */
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.Dashboard }))
);
const ProjectsPage = lazy(() =>
  import("./pages/ProjectsPage").then((m) => ({ default: m.ProjectsPage }))
);
const ProjectPage = lazy(() =>
  import("./pages/ProjectPage").then((m) => ({ default: m.ProjectPage }))
);
const ChapterDetail = lazy(() =>
  import("./pages/ChapterDetail").then((m) => ({ default: m.ChapterDetail }))
);
const WorkerPage = lazy(() =>
  import("./pages/WorkerPage").then((m) => ({ default: m.WorkerPage }))
);
const TasksPage = lazy(() =>
  import("./pages/TasksPage").then((m) => ({ default: m.TasksPage }))
);
const PromptsPage = lazy(() =>
  import("./pages/PromptsPage").then((m) => ({ default: m.PromptsPage }))
);
const ModelConfigPage = lazy(() => import("./pages/ModelConfigPage"));
const ModelProviderDetailPage = lazy(() => import("./pages/ModelProviderDetailPage"));
const StudyLibraryPage = lazy(() =>
  import("./pages/StudyLibraryPage").then((m) => ({ default: m.StudyLibraryPage }))
);
const StudyBookGraphPage = lazy(() =>
  import("./pages/StudyLibraryPage").then((m) => ({ default: m.StudyBookGraphPage }))
);
const StudyPage = lazy(() =>
  import("./pages/StudyPage").then((m) => ({ default: m.StudyPage }))
);
const DiscussionPage = lazy(() =>
  import("./pages/DiscussionPage").then((m) => ({ default: m.DiscussionPage }))
);
const MemoryShelfPage = lazy(() =>
  import("./pages/MemoryShelfPage").then((m) => ({ default: m.MemoryShelfPage }))
);
const MemoryArchivePage = lazy(() =>
  import("./pages/MemoryShelfPage").then((m) => ({ default: m.MemoryArchivePage }))
);
const AgentMemoryPage = lazy(() =>
  import("./pages/AgentMemoryPage").then((m) => ({ default: m.AgentMemoryPage }))
);
const BehaviorPage = lazy(() =>
  import("./pages/BehaviorPage").then((m) => ({ default: m.BehaviorPage }))
);
const GraphPage = lazy(() =>
  import("./pages/GraphPage").then((m) => ({ default: m.GraphPage }))
);
const GraphsPage = lazy(() =>
  import("./pages/GraphsPage").then((m) => ({ default: m.GraphsPage }))
);
const GraphNetworkPage = lazy(() =>
  import("./pages/GraphNetworkPage").then((m) => ({ default: m.GraphNetworkPage }))
);
const ReviewCommentsPage = lazy(() =>
  import("./pages/ReviewCommentsPage").then((m) => ({ default: m.ReviewCommentsPage }))
);
const ReaderAgentsPage = lazy(() =>
  import("./pages/ReaderAgentsPage").then((m) => ({ default: m.ReaderAgentsPage }))
);
const ReaderAgentDetailPage = lazy(() =>
  import("./pages/ReaderAgentDetailPage").then((m) => ({ default: m.ReaderAgentDetailPage }))
);
const AutomationAuditPage = lazy(() =>
  import("./pages/AutomationAuditPage").then((m) => ({ default: m.AutomationAuditPage }))
);
const GenrePromptMatrixPage = lazy(() =>
  import("./pages/GenrePromptMatrixPage").then((m) => ({ default: m.GenrePromptMatrixPage }))
);
const ModelObservabilityPanel = lazy(() =>
  import("./components/models/ModelObservabilityPanel")
);
const AuditLogPage = lazy(() =>
  import("./pages/AuditLogPage").then((m) => ({ default: m.AuditLogPage }))
);
const NotFound = lazy(() =>
  import("./pages/NotFound").then((m) => ({ default: m.NotFound }))
);

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
  const location = useLocation();
  return (
    <AppShell>
      <DevApiBaseBanner />
      <BackendHealthBanner />
      <Suspense fallback={<PageSkeleton />}>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
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
            {/* P0-拆书书架: /study/library 是唯一主入口 (书架+上传+删除+分类+诊断).
             * 旧 /study 重定向到 /study/library, 旧 StudyPage 仍可独立访问.
             * 新增 /study/upload 兼容旧页面的直达链接. */}
            <Route path="/study" element={<Navigate to="/study/library" replace />} />
            <Route path="/study/upload" element={<StudyPage />} />
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
        </AnimatePresence>
      </Suspense>
    </AppShell>
  );
}
