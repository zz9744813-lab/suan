// P0 返工 Phase 4.4: 图谱书架 + 图谱详情
//
// 两段式布局：
//   1. 上方「按项目书架」: 列出所有 project, 调 GET /api/graph/{pid}/diagnostics
//      - 空项目 → 渲染 issues + recommended_actions (一键跳转修复)
//      - 有图项目 → 渲染节点/边统计 + 节点种类分布 + 贡献过的书
//   2. 下方「按书列表」: 沿用旧逻辑, 调 GET /api/graphs/books
//      - 继续是 R22 (单书) 入口, 走 /graphs/:materialId/network
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listGraphBooks, listProjects, getGraphDiagnostics } from "../api";
import type { GraphDiagnosticsRead, Project } from "../types";

type GraphBookSummary = {
  material_id: number;
  title: string;
  author?: string | null;
  status: string;
  node_count: number;
  edge_count: number;
  character_count: number;
  event_count: number;
  foreshadow_count: number;
  behavior_pattern_count: number;
  writing_technique_count: number;
  last_built_at?: string | null;
};

const SEVERITY_PILL: Record<string, string> = {
  info: "pill tiny",
  warn: "pill tiny warn",
  error: "pill tiny error",
};

export function GraphsPage() {
  const [books, setBooks] = useState<GraphBookSummary[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [diag, setDiag] = useState<Record<number, GraphDiagnosticsRead | null>>({});
  const navigate = useNavigate();

  // ── 数据加载 ─────────────────────────────────────────────
  useEffect(() => {
    listGraphBooks({ status: filter === "all" ? undefined : filter }).then(setBooks).catch(() => {});
  }, [filter]);

  useEffect(() => {
    listProjects()
      .then((r: any) => {
        // api.client.ts 已经自动 unwrap 了 {data: ...}, r 直接是 Project[]
        const list: Project[] = Array.isArray(r) ? r : (r?.data ?? []);
        setProjects(list);
        // 每个项目并联拉一次 diagnostics
        return Promise.all(
          list.map((p) =>
            getGraphDiagnostics(p.id)
              .then((d: any) => [p.id, d?.data ?? d ?? null] as const)
              .catch(() => [p.id, null] as const),
          ),
        );
      })
      .then((entries) => {
        const map: Record<number, GraphDiagnosticsRead | null> = {};
        for (const [pid, d] of entries) map[pid] = d;
        setDiag(map);
      })
      .catch(() => {});
  }, []);

  const filtered = books.filter((b) => !search || b.title.toLowerCase().includes(search.toLowerCase()));
  const ready = filtered.filter((b) => b.status === "ready");
  const building = filtered.filter((b) => b.status === "building");
  const failed = filtered.filter((b) => b.status === "failed" || b.status === "stale");

  return (
    <div className="main-body">
      {/* ============== Section 1: 按项目书架 ============== */}
      <div style={{ padding: "20px 24px 0" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🌐 图谱书架</h2>
          <span className="muted small">按项目聚合 · 空图谱会告诉你"为什么空"和"怎么修"</span>
        </div>

        {projects.length === 0 ? (
          <div className="muted small">暂无项目</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
            {projects.map((p) => {
              const d = diag[p.id];
              return (
                <ProjectShelfCard
                  key={p.id}
                  project={p}
                  diag={d}
                  navigate={navigate}
                  onOpen={() => navigate(`/graphs?project_id=${p.id}`)}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* ============== Section 2: 按书列表 (旧逻辑) ============== */}
      <div style={{ marginTop: 32 }}>
        <div style={{ display: "flex", gap: 12, padding: "0 24px 12px", alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>📚 按书查看</h2>
          <input
            className="input"
            placeholder="搜索书名"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ maxWidth: 240 }}
          />
          <div style={{ display: "flex", gap: 6 }}>
            {["all", "ready", "building", "failed"].map((s) => (
              <button key={s} className={`pill ${filter === s ? "primary" : ""}`} onClick={() => setFilter(s)}>
                {s === "all" ? "全部" : s === "ready" ? "已完成" : s === "building" ? "生成中" : "失败"}
              </button>
            ))}
          </div>
          <span className="muted small" style={{ marginLeft: "auto" }}>{filtered.length} 本</span>
        </div>

        {filtered.length === 0 ? (
          <div className="card" style={{ textAlign: "center", padding: 40, margin: "0 24px" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🌐</div>
            <div className="muted">暂无图谱数据</div>
            <div className="muted small">对参考书运行 DeepStudy 后，图谱将自动生成</div>
          </div>
        ) : (
          <>
            {ready.length > 0 && (
              <div style={{ padding: "0 24px 16px" }}>
                <div className="muted small" style={{ marginBottom: 8 }}>已完成 ({ready.length})</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
                  {ready.map((b) => (
                    <div
                      key={b.material_id}
                      className="card"
                      style={{ cursor: "pointer", padding: 14 }}
                      onClick={() => navigate(`/graphs/${b.material_id}/network`)}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                        <b style={{ fontSize: 14 }}>{b.title}</b>
                        <span className="pill tiny ok">ready</span>
                      </div>
                      <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11, color: "var(--text-muted)", flexWrap: "wrap" }}>
                        <span>节点 {b.node_count}</span>
                        <span>边 {b.edge_count}</span>
                        <span>人物 {b.character_count}</span>
                        <span>事件 {b.event_count}</span>
                        {b.behavior_pattern_count > 0 && <span>行为 {b.behavior_pattern_count}</span>}
                        {b.writing_technique_count > 0 && <span>技巧 {b.writing_technique_count}</span>}
                      </div>
                      {b.last_built_at && <div className="muted tiny" style={{ marginTop: 4 }}>{new Date(b.last_built_at).toLocaleDateString()}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {building.length > 0 && (
              <div style={{ padding: "0 24px 16px" }}>
                <div className="muted small" style={{ marginBottom: 8 }}>生成中 ({building.length})</div>
                {building.map((b) => (
                  <div key={b.material_id} className="card" style={{ padding: 10, marginBottom: 6 }}>
                    <span>{b.title}</span>
                    <span className="pill tiny warn" style={{ marginLeft: 8 }}>building</span>
                  </div>
                ))}
              </div>
            )}

            {failed.length > 0 && (
              <div style={{ padding: "0 24px 16px" }}>
                <div className="muted small" style={{ marginBottom: 8 }}>失败 ({failed.length})</div>
                {failed.map((b) => (
                  <div key={b.material_id} className="card" style={{ padding: 10, marginBottom: 6, borderColor: "var(--danger)" }}>
                    <span>{b.title}</span>
                    <span className="pill tiny error" style={{ marginLeft: 8 }}>{b.status}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── 单个项目书架卡片 ───────────────────────────────────────
function ProjectShelfCard({
  project,
  diag,
  navigate,
  onOpen,
}: {
  project: Project;
  diag: GraphDiagnosticsRead | null | undefined;
  navigate: (path: string) => void;
  onOpen: () => void;
}) {
  // diag 还在加载
  if (diag === undefined) {
    return (
      <div className="card" style={{ padding: 14, opacity: 0.5 }}>
        <div className="muted small">加载中…</div>
      </div>
    );
  }
  // 后端报错 / 项目不存在 diagnostics
  if (diag === null) {
    return (
      <div className="card" style={{ padding: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
          <b style={{ fontSize: 14 }}>{project.name}</b>
          <span className="pill tiny warn">诊断失败</span>
        </div>
        <div className="muted tiny" style={{ marginTop: 6 }}>无法获取图谱诊断, 跳过</div>
      </div>
    );
  }

  // ── 空状态 ──
  if (diag.is_empty) {
    return (
      <div className="card" style={{ padding: 14, borderColor: "var(--warning)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 6 }}>
          <div>
            <b style={{ fontSize: 14 }}>{project.name}</b>
            <div className="muted tiny">空图谱</div>
          </div>
          <span className="pill tiny warn">empty</span>
        </div>
        {/* P0 返工 Phase 5.5: 上次物化错误 (不静默跳过) */}
        {diag.last_materialise_error && (
          <div
            style={{
              fontSize: 11,
              padding: "6px 8px",
              marginBottom: 6,
              borderRadius: 4,
              background: "var(--danger-bg, #fdd)",
              color: "var(--danger-text, #900)",
            }}
          >
            ⚠️ {diag.last_materialise_error}
          </div>
        )}
        {/* Issues */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8 }}>
          {diag.issues.map((iss, i) => (
            <div key={i} style={{ display: "flex", alignItems: "start", gap: 6, fontSize: 12 }}>
              <span className={SEVERITY_PILL[iss.severity] ?? "pill tiny"}>{iss.severity}</span>
              <span style={{ flex: 1 }}>
                {iss.message}
                {iss.fix_hint && <div className="muted tiny" style={{ marginTop: 2 }}>💡 {iss.fix_hint}</div>}
              </span>
            </div>
          ))}
        </div>
        {/* Recommended actions */}
        {diag.recommended_actions.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 10 }}>
            {diag.recommended_actions
              .sort((a, b) => a.priority - b.priority)
              .map((act, i) => (
                <button
                  key={i}
                  className="pill primary"
                  style={{ fontSize: 12, cursor: "pointer", textAlign: "left" }}
                  onClick={() => {
                    if (act.method === "POST") {
                      // 一键物化 — 调 backend, 然后刷新当前页
                      fetch(`/api/graph/${project.id}/materialise`, { method: "POST" })
                        .then(() => window.location.reload())
                        .catch(() => alert("物化失败"));
                    } else {
                      navigate(act.target);
                    }
                  }}
                >
                  ➜ {act.label}
                </button>
              ))}
          </div>
        )}
      </div>
    );
  }

  // ── 有图状态 ──
  const kindEntries = Object.entries(diag.nodes_by_kind).sort((a, b) => b[1] - a[1]);
  return (
    <div
      className="card"
      style={{ padding: 14, cursor: "pointer" }}
      onClick={onOpen}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
        <div>
          <b style={{ fontSize: 14 }}>{project.name}</b>
          {diag.last_materialised_at && (
            <div className="muted tiny" style={{ marginTop: 2 }}>
              最近物化 {new Date(diag.last_materialised_at).toLocaleString()}
            </div>
          )}
        </div>
        <span className="pill tiny ok">{diag.node_count} 节点</span>
      </div>

      <div style={{ display: "flex", gap: 12, marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>
        <span>📍 节点 {diag.node_count}</span>
        <span>🔗 边 {diag.edge_count}</span>
      </div>

      {/* 节点按 kind 分布 */}
      {kindEntries.length > 0 && (
        <div style={{ display: "flex", gap: 4, marginTop: 8, flexWrap: "wrap" }}>
          {kindEntries.map(([k, n]) => (
            <span key={k} className="pill tiny" title={k}>
              {k}: {n}
            </span>
          ))}
        </div>
      )}

      {/* 贡献过的书 */}
      {diag.contributing_materials.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="muted tiny">贡献的书:</div>
          <div style={{ display: "flex", gap: 4, marginTop: 2, flexWrap: "wrap" }}>
            {diag.contributing_materials.slice(0, 3).map((m) => (
              <span key={m.id} className="pill tiny" title={m.title}>
                📖 {m.title.slice(0, 8)} ({m.node_count})
              </span>
            ))}
            {diag.contributing_materials.length > 3 && (
              <span className="muted tiny">+{diag.contributing_materials.length - 3}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
