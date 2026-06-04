/**
 * MemoryShelfPage + MemoryArchivePage — 记忆书架 (P0 stub)
 *
 * 完整实现是 P3 (04_P3) 范围. P0 行为:
 *   - /memory/library 渲染旧的 MemoryPage (保持现有功能)
 *   - /memory/:projectId 渲染旧的 MemoryPage 但带 project filter
 *
 * P3 一次性把这里换成 ShelfLayout 风格. 在此之前用户体感零变化.
 */
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MemoryPage } from "./MemoryPage";
import { ShelfBreadcrumb } from "../components/shelf";

export function MemoryShelfPage() {
  // P0 阶段: 直接渲染旧 MemoryPage, P3 替换成 ShelfLayout 书架
  return <MemoryPage />;
}

export function MemoryArchivePage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  useEffect(() => {
    // P0 兜底: 把 projectId 拼到 query, P3 替换为真正的记忆档案馆
    if (projectId) navigate(`/memory?project=${projectId}`, { replace: true });
  }, [navigate, projectId]);
  return (
    <div style={{ padding: 24 }}>
      <ShelfBreadcrumb
        backTo="/memory"
        backLabel="返回记忆书架"
        items={[{ label: `记忆档案 #${projectId ?? ""}` }]}
      />
      <p className="muted">记忆档案馆骨架 (P0), 完整版在 P3 实现…</p>
    </div>
  );
}
