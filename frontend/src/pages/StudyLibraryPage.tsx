/**
 * StudyLibraryPage — 拆书书架 (P0 stub)
 *
 * P0 (01 §6) 已经把路由 `/study/library` 放进声明, 旧 `/study`
 * 重定向到这里. 但完整的拆书书架实现是 P2 (03_P2_拆书书架) 范围,
 * 所以这个 P0 版本直接复用旧 StudyPage 的实现 — 用户从 /study
 * 自动跳到 /study/library, 视觉跟以前一样, 不会感觉到差异.
 * 等 P2 把 StudyPage 改成 ShelfLayout 风格时, 这里换 import 即可.
 */
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { StudyPage } from "./StudyPage";
import { ShelfBreadcrumb } from "../components/shelf";

export function StudyLibraryPage() {
  // P0 阶段: 直接渲染旧 StudyPage, P2 替换成 ShelfLayout 书架
  return <StudyPage />;
}

/**
 * StudyBookGraphPage — 单书知识网络图谱 (P0 stub)
 *
 * 完整实现是 P2 范围, P0 只接路由. materialId 在 URL 里, 跟旧的
 * `/graph` 路由 (基于 project_id) 协议不同, 不能直接复用 GraphPage.
 * P0 这里把 materialId 写到 sessionStorage, 旧的 GraphPage 在 P2
 * 替换前先忽略这个标记 — 不会破坏现有 /graph 行为.
 */
export function StudyBookGraphPage() {
  const navigate = useNavigate();
  const { materialId } = useParams();
  useEffect(() => {
    if (materialId) {
      // 暂存, P2 的真 GraphPage 接班时读这个值定位拆书材料
      try { sessionStorage.setItem("study.materialId", materialId); } catch { /* private mode */ }
    }
    // P0 兜底: 跳到旧 /graph 拿当前项目图谱, P2 替换为单书知识网络
    navigate("/graph", { replace: true });
  }, [navigate, materialId]);
  return (
    <div style={{ padding: 24 }}>
      <ShelfBreadcrumb
        backTo="/study/library"
        backLabel="返回拆书书架"
        items={[{ label: `知识图谱 #${materialId ?? ""}` }]}
      />
      <p className="muted">单书知识网络骨架 (P0), 完整版在 P2 实现…</p>
    </div>
  );
}
