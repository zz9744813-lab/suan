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
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <AppShell>
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
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  );
}
