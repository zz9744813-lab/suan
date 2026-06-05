import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getGraphNetwork, getGraphNodeDetail, getGraphEdgeDetail } from "../api";

// Node colors by type
const NODE_COLORS: Record<string, string> = {
  book: "#d4af37", character: "#5b9bd5", location: "#ed7d31", faction: "#c0504d",
  item: "#d4af37", world_rule: "#8497b0", event: "#70ad47", scene_beat: "#a5a5a5",
  foreshadow: "#ffc000", behavior_pattern: "#9b59b6", writing_technique: "#5dc1cf",
};

const STAGE_LABELS: Record<string, string> = {
  entity_extract: "实体抽取", event_extract: "事件抽取", relationship_analyze: "关系分析",
  foreshadow_analyze: "伏笔分析", behavior_pattern_mine: "行为模式", technique_mine: "技巧",
  graph_finalize: "图谱整理",
};

type GraphNode = { id: number; node_key: string; node_type: string; label: string; summary?: string; importance: number; confidence: number; source_stage?: string; evidence_json?: any; x?: number; y?: number };
type GraphEdge = { id: number; edge_key: string; source_node_key: string; target_node_key: string; edge_type: string; label: string; summary?: string; weight: number; confidence: number; source_stage?: string; evidence_json?: any };

export function GraphNetworkPage() {
  const { materialId } = useParams<{ materialId: string }>();
  const navigate = useNavigate();
  const [graph, setGraph] = useState<any>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [selectedEdge, setSelectedEdge] = useState<any>(null);
  const [nodeDetail, setNodeDetail] = useState<any>(null);
  const [edgeDetail, setEdgeDetail] = useState<any>(null);
  const [search, setSearch] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);

  const mid = Number(materialId);

  useEffect(() => {
    getGraphNetwork(mid).then(data => {
      setGraph(data.graph);
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    }).catch(() => {});
  }, [mid]);

  // Simple force layout
  useEffect(() => {
    if (nodes.length === 0) return;
    // Assign random positions if none exist
    const W = 900, H = 600;
    const cx = W / 2, cy = H / 2;
    nodes.forEach((n: any) => {
      if (n.x == null) { n.x = cx + (Math.random() - 0.5) * 500; n.y = cy + (Math.random() - 0.5) * 400; }
    });
    // Simple force simulation (a few iterations)
    for (let iter = 0; iter < 30; iter++) {
      const fx: Record<number, number> = {}, fy: Record<number, number> = {};
      nodes.forEach(n => { fx[n.id] = 0; fy[n.id] = 0; });
      // Repulsion
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = (nodes[j] as any).x - (nodes[i] as any).x;
          const dy = (nodes[j] as any).y - (nodes[i] as any).y;
          const dist = Math.max(1, Math.sqrt(dx*dx + dy*dy));
          const f = 2000 / (dist * dist);
          fx[nodes[i].id] -= f * dx / dist; fy[nodes[i].id] -= f * dy / dist;
          fx[nodes[j].id] += f * dx / dist; fy[nodes[j].id] += f * dy / dist;
        }
      }
      // Attraction
      edges.forEach(e => {
        const sn = nodes.find(n => n.node_key === e.source_node_key);
        const tn = nodes.find(n => n.node_key === e.target_node_key);
        if (!sn || !tn) return;
        const dx = (tn as any).x - (sn as any).x;
        const dy = (tn as any).y - (sn as any).y;
        const dist = Math.max(1, Math.sqrt(dx*dx + dy*dy));
        const f = dist * 0.01;
        fx[sn.id] += f * dx / dist; fy[sn.id] += f * dy / dist;
        fx[tn.id] -= f * dx / dist; fy[tn.id] -= f * dy / dist;
      });
      // Apply + center gravity
      nodes.forEach(n => {
        fx[n.id] += (cx - (n as any).x) * 0.02;
        fy[n.id] += (cy - (n as any).y) * 0.02;
        (n as any).x = Math.max(30, Math.min(W - 30, (n as any).x + fx[n.id] * 0.3));
        (n as any).y = Math.max(30, Math.min(H - 30, (n as any).y + fy[n.id] * 0.3));
      });
    }
    setNodes([...nodes]);
  }, [nodes.length, edges.length]);

  const handleNodeClick = async (n: GraphNode) => {
    setSelectedNode(n);
    setSelectedEdge(null);
    setEdgeDetail(null);
    try { const d = await getGraphNodeDetail(mid, n.id); setNodeDetail(d); } catch { setNodeDetail(null); }
  };

  const handleEdgeClick = async (e: GraphEdge) => {
    setSelectedEdge(e);
    setSelectedNode(null);
    setNodeDetail(null);
    try { const d = await getGraphEdgeDetail(mid, e.id); setEdgeDetail(d); } catch { setEdgeDetail(null); }
  };

  return (
    <div className="main-body" style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Top bar */}
      <div style={{ display: "flex", gap: 12, padding: "8px 16px", alignItems: "center", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button onClick={() => navigate("/graphs")} className="link">← 返回</button>
        <b style={{ fontSize: 14 }}>{graph?.title || "知识网络"}</b>
        <span className="pill tiny">{graph?.status}</span>
        <span className="muted tiny">{nodes.length} 节点 · {edges.length} 边</span>
        <span className="spacer" />
        <input className="input" placeholder="搜索节点" value={search} onChange={e => setSearch(e.target.value)} style={{ width: 180, fontSize: 12 }} />
      </div>

      {/* Main area: SVG + detail panel */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <svg ref={svgRef} width="100%" height="100%" viewBox="0 0 900 600" preserveAspectRatio="xMidYMid meet" style={{ flex: 1, background: "var(--bg-base)" }}>
          {/* Edges */}
          {edges.map(e => {
            const sn = nodes.find(n => n.node_key === e.source_node_key);
            const tn = nodes.find(n => n.node_key === e.target_node_key);
            if (!sn || !tn) return null;
            const isSelected = selectedEdge?.id === e.id;
            return (
              <line key={e.id} x1={(sn as any).x} y1={(sn as any).y} x2={(tn as any).x} y2={(tn as any).y}
                stroke={isSelected ? "var(--accent)" : "var(--border)"} strokeWidth={isSelected ? 2.5 : Math.max(0.5, e.weight * 1.5)}
                opacity={isSelected ? 1 : 0.6} style={{ cursor: "pointer" }}
                onClick={() => handleEdgeClick(e)}>
                <title>{e.label} ({e.edge_type}) · conf {e.confidence.toFixed(2)}</title>
              </line>
            );
          })}
          {/* Nodes */}
          {nodes.map(n => {
            const isSelected = selectedNode?.id === n.id;
            const r = 4 + n.importance * 10;
            return (
              <g key={n.id} style={{ cursor: "pointer" }} onClick={() => handleNodeClick(n)}>
                <circle cx={(n as any).x} cy={(n as any).y} r={r}
                  fill={NODE_COLORS[n.node_type] || "#999"} stroke={isSelected ? "#fff" : "none"} strokeWidth={2} />
                <text x={(n as any).x} y={(n as any).y - r - 3} textAnchor="middle" fontSize={10} fill="var(--text-secondary)">{n.label.slice(0, 8)}</text>
                <title>{n.label} ({n.node_type}) · imp {n.importance.toFixed(2)}</title>
              </g>
            );
          })}
        </svg>

        {/* Detail panel */}
        <div style={{ width: 320, borderLeft: "1px solid var(--border)", padding: 12, overflowY: "auto", flexShrink: 0, fontSize: 12 }}>
          {selectedNode && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", background: NODE_COLORS[selectedNode.node_type] || "#999", display: "inline-block" }} />
                <b>{selectedNode.label}</b>
                <span className="pill tiny">{selectedNode.node_type}</span>
              </div>
              {selectedNode.summary && <div className="muted small" style={{ marginBottom: 8 }}>{selectedNode.summary}</div>}
              <div className="muted tiny">置信度: {(selectedNode.confidence * 100).toFixed(0)}% · 重要度: {(selectedNode.importance * 100).toFixed(0)}%</div>
              {selectedNode.source_stage && <div className="muted tiny">来源: {STAGE_LABELS[selectedNode.source_stage] || selectedNode.source_stage}</div>}
              {nodeDetail?.related_edges && nodeDetail.related_edges.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div className="muted tiny" style={{ marginBottom: 4 }}>关联关系 ({nodeDetail.related_edges.length})</div>
                  {nodeDetail.related_edges.map((re: any) => (
                    <div key={re.id} className="muted tiny" style={{ padding: "2px 0" }}>{re.label} ({re.edge_type})</div>
                  ))}
                </div>
              )}
            </div>
          )}
          {selectedEdge && (
            <div>
              <div style={{ marginBottom: 8 }}>
                <b>{selectedEdge.label}</b>
                <span className="pill tiny" style={{ marginLeft: 6 }}>{selectedEdge.edge_type}</span>
              </div>
              {selectedEdge.summary && <div className="muted small" style={{ marginBottom: 8 }}>{selectedEdge.summary}</div>}
              <div className="muted tiny">权重: {selectedEdge.weight.toFixed(2)} · 置信度: {(selectedEdge.confidence * 100).toFixed(0)}%</div>
              {selectedEdge.source_stage && <div className="muted tiny">来源: {STAGE_LABELS[selectedEdge.source_stage] || selectedEdge.source_stage}</div>}
              {edgeDetail?.evidence_json && (
                <div style={{ marginTop: 8 }}>
                  <div className="muted tiny" style={{ marginBottom: 4 }}>证据</div>
                  {((edgeDetail.evidence_json as any[]) || []).slice(0, 3).map((ev: any, i: number) => (
                    <div key={i} className="muted tiny" style={{ padding: "2px 0", borderLeft: "2px solid var(--border)", paddingLeft: 8 }}>
                      {ev.chapter_index && <span>第{ev.chapter_index}章 </span>}
                      {ev.quote && <span>「{ev.quote.slice(0, 80)}」</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {!selectedNode && !selectedEdge && (
            <div className="muted small">点击节点或连线查看详情</div>
          )}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, padding: "6px 16px", borderTop: "1px solid var(--border)", flexShrink: 0, flexWrap: "wrap", fontSize: 11 }}>
        {Object.entries(NODE_COLORS).filter(([k]) => k !== "book" && k !== "scene_beat" && k !== "world_rule").map(([type, color]) => (
          <span key={type} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}
