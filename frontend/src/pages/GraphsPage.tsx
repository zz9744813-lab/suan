import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listGraphBooks } from "../api";

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

export function GraphsPage() {
  const [books, setBooks] = useState<GraphBookSummary[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    listGraphBooks({ status: filter === "all" ? undefined : filter }).then(setBooks).catch(() => {});
  }, [filter]);

  const filtered = books.filter(b => !search || b.title.toLowerCase().includes(search.toLowerCase()));

  const ready = filtered.filter(b => b.status === "ready");
  const building = filtered.filter(b => b.status === "building");
  const failed = filtered.filter(b => b.status === "failed" || b.status === "stale");

  return (
    <div className="main-body">
      {/* Compact header */}
      <div style={{ display: "flex", gap: 12, padding: "12px 24px", alignItems: "center", flexWrap: "wrap" }}>
        <input className="input" placeholder="搜索书名" value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 280 }} />
        <div style={{ display: "flex", gap: 6 }}>
          {["all","ready","building","failed"].map(s => (
            <button key={s} className={`pill ${filter===s?"primary":""}`} onClick={()=>setFilter(s)}>
              {s==="all"?"全部":s==="ready"?"已完成":s==="building"?"生成中":"失败"}
            </button>
          ))}
        </div>
        <span className="muted small" style={{ marginLeft: "auto" }}>{filtered.length} 本</span>
      </div>

      {filtered.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40, margin: 24 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🌐</div>
          <div className="muted">暂无图谱数据</div>
          <div className="muted small">对参考书运行 DeepStudy 后，图谱将自动生成</div>
        </div>
      ) : (
        <>
          {/* Ready books */}
          {ready.length > 0 && (
            <div style={{ padding: "0 24px 16px" }}>
              <div className="muted small" style={{ marginBottom: 8 }}>已完成 ({ready.length})</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
                {ready.map(b => (
                  <div key={b.material_id} className="card" style={{ cursor: "pointer", padding: 14 }} onClick={() => navigate(`/graphs/${b.material_id}/network`)}>
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

          {/* Building */}
          {building.length > 0 && (
            <div style={{ padding: "0 24px 16px" }}>
              <div className="muted small" style={{ marginBottom: 8 }}>生成中 ({building.length})</div>
              {building.map(b => (
                <div key={b.material_id} className="card" style={{ padding: 10, marginBottom: 6 }}>
                  <span>{b.title}</span>
                  <span className="pill tiny warn" style={{ marginLeft: 8 }}>building</span>
                </div>
              ))}
            </div>
          )}

          {/* Failed */}
          {failed.length > 0 && (
            <div style={{ padding: "0 24px 16px" }}>
              <div className="muted small" style={{ marginBottom: 8 }}>失败 ({failed.length})</div>
              {failed.map(b => (
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
  );
}
