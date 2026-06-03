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
import { StudyPage } from "./pages/StudyPage";
import { DiscussionPage } from "./pages/DiscussionPage";
import { MemoryPage } from "./pages/MemoryPage";
import { BehaviorPage } from "./pages/BehaviorPage";
import { GraphPage } from "./pages/GraphPage";
import { NotFound } from "./pages/NotFound";

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

export default function App() {
  return (
    <AppShell>
      <DevApiBaseBanner />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:pid" element={<ProjectPage />} />
        <Route path="/projects/:pid/chapters/:cid" element={<ChapterDetail />} />
        <Route path="/worker" element={<WorkerPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/study" element={<StudyPage />} />
        <Route path="/behavior" element={<BehaviorPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/discussion" element={<DiscussionPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  );
}
