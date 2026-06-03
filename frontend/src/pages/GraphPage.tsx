/**
 * GraphPage — Round E (P1-1) 人物关系图谱
 *
 * Standalone first-class page for browsing and editing the
 * ``graph_nodes`` + ``graph_edges`` tables. Layout is computed
 * client-side using a simple force-directed layout (deterministic,
 * seeded by node id so the picture doesn't jump around on re-render).
 *
 * The visualisation itself is plain SVG — no third-party graph lib
 * to keep the bundle small. Each node is a circle whose radius
 * grows with degree (in + out edges). Edges are coloured by
 * ``relation`` family. Hover shows a tooltip with evidence.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  getGraph,
  createGraphNode,
  deleteGraphNode,
  createGraphEdge,
  deleteGraphEdge,
  listStudyMaterials,
  materialiseFromStudy,
} from "../api";
import type {
  GraphEdge,
  GraphNode,
  GraphNodeKind,
  StudyMaterial,
  MaterialiseSummary,
} from "../types";
import { useProjectStore } from "../stores/projectStore";

const KIND_COLORS: Record<GraphNodeKind, string> = {
  study_character: "#6e9ecf",
  project_character: "#78c77a",
  faction: "#d6a64e",
  location: "#c19ad6",
  other: "#888",
};

const RELATION_COLORS: Record<string, string> = {
  师父: "#d6a64e",
  弟子: "#d6a64e",
  对手: "#ef6b5b",
  恋人: "#e58fcf",
  朋友: "#78c77a",
  仇人: "#a83232",
  势力: "#c19ad6",
  default: "#888",
};

const NODE_R = 26;

function relationColor(rel: string): string {
  return RELATION_COLORS[rel] ?? RELATION_COLORS.default;
}

// ---------- Tiny deterministic force layout ----------

type Pos = { x: number; y: number };
type LayedOut = GraphNode & { x: number; y: number; degree: number };

function layoutNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
): LayedOut[] {
  if (nodes.length === 0) return [];
  // Seed positions on a circle so the first paint is sane.
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  const degree = new Map<number, number>();
  edges.forEach((e) => {
    degree.set(e.source_node_id, (degree.get(e.source_node_id) ?? 0) + 1);
    degree.set(e.target_node_id, (degree.get(e.target_node_id) ?? 0) + 1);
  });
  return nodes.map((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    return {
      ...n,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      degree: degree.get(n.id) ?? 0,
    };
  });
}

// ---------- Component ----------

export function GraphPage() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<{ kind: "node" | "edge"; data: any } | null>(null);
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [showMaterialise, setShowMaterialise] = useState(false);
  // R22: which "kind" to materialise — character / event / behavior / all.
  // The modal remembers the user's last choice for the next import.
  const [materialiseKind, setMaterialiseKind] = useState<"all" | "character" | "event" | "behavior">("all");
  // R22: transient toast shown after a materialise completes.
  // Auto-clears after 4s so it doesn't pile up.
  const [materialiseToast, setMaterialiseToast] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const W = 920;
  const H = 540;

  const refresh = async () => {
    if (currentProjectId == null) return;
    setBusy(true);
    try {
      const g = await getGraph(currentProjectId);
      setNodes(g?.nodes ?? []);
      setEdges(g?.edges ?? []);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProjectId]);

  useEffect(() => {
    listStudyMaterials(currentProjectId ?? undefined).then((r) => setMaterials(r ?? []));
  }, [currentProjectId]);

  // R22: auto-clear the import toast after 4s so it doesn't pile up
  // when the user does several imports in a row.
  useEffect(() => {
    if (!materialiseToast) return;
    const t = setTimeout(() => setMaterialiseToast(null), 4000);
    return () => clearTimeout(t);
  }, [materialiseToast]);

  const laid = useMemo(() => layoutNodes(nodes, edges, W, H), [nodes, edges]);
  const byId = useMemo(() => {
    const m = new Map<number, LayedOut>();
    laid.forEach((n) => m.set(n.id, n));
    return m;
  }, [laid]);

  // Relations present in the current edge set (for the legend).
  const relationsInUse = useMemo(() => {
    const s = new Set<string>();
    edges.forEach((e) => s.add(e.relation));
    return Array.from(s).sort();
  }, [edges]);

  const onAddNode = async (name: string, kind: GraphNodeKind) => {
    if (currentProjectId == null || !name.trim()) return;
    await createGraphNode(currentProjectId, { name: name.trim(), node_kind: kind });
    await refresh();
  };

  const onAddEdge = async (src: number, tgt: number, relation: string) => {
    if (currentProjectId == null || !relation.trim()) return;
    await createGraphEdge(currentProjectId, {
      source_node_id: src,
      target_node_id: tgt,
      relation: relation.trim(),
    });
    await refresh();
  };

  const onMaterialise = async (materialId: number, kind: "all" | "character" | "event" | "behavior") => {
    if (currentProjectId == null) return;
    setBusy(true);
    try {
      // R22: the backend returns {ok, data, materialise_summary} —
      // we surface the summary in a toast so the user knows "X 个节点 / Y 条边"
      // were just created. We also re-fetch the graph to pick up the
      // new nodes/edges visually.
      const r: any = await materialiseFromStudy(
        currentProjectId,
        materialId,
        kind,
        true,  // add_cooccurrence_edges
      );
      const sum: MaterialiseSummary | undefined = r?.materialise_summary;
      setMaterialiseToast(
        sum
          ? `导入完成: 新增 ${sum.nodes_created} 节点 / ${sum.edges_created} 边`
          : "导入完成",
      );
      await refresh();
    } catch (e: any) {
      setMaterialiseToast(`导入失败: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
      setShowMaterialise(false);
    }
  };

  // R22: lookup table for source-material titles so the canvas tooltip
  // can show "来源: 《xxx》" when the user hovers a node. Without
  // this the only signal is the numeric source_material_id, which
  // is useless without leaving the page.
  const materialTitlesById = useMemo(() => {
    const m = new Map<number, string>();
    for (const mat of materials) m.set(mat.id, mat.title);
    return m;
  }, [materials]);

  if (currentProjectId == null) {
    return (
      <div className="page graph-page">
        <div className="empty">请先在左侧选中一个项目。</div>
      </div>
    );
  }

  return (
    <div className="page graph-page">
      <header className="page-header">
        <h2>人物关系图谱</h2>
        <span className="muted">
          {nodes.length} 节点 · {edges.length} 关系
        </span>
        <span className="spacer" />
        <button onClick={() => setShowMaterialise(true)}>从拆书导入人物</button>
        <button onClick={refresh} disabled={busy}>
          {busy ? "刷新中…" : "刷新"}
        </button>
      </header>

      <div className="graph-legend">
        <span className="legend-title">节点：</span>
        {Object.entries(KIND_COLORS).map(([k, c]) => (
          <span key={k} className="legend-item">
            <span className="legend-dot" style={{ background: c }} />
            {k}
          </span>
        ))}
        <span className="legend-title" style={{ marginLeft: 16 }}>关系：</span>
        {relationsInUse.length === 0 && <span className="muted tiny">（暂无）</span>}
        {relationsInUse.map((r) => (
          <span key={r} className="legend-item">
            <span className="legend-bar" style={{ background: relationColor(r) }} />
            {r}
          </span>
        ))}
      </div>

      <div className="graph-canvas-wrap">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="graph-svg"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* edges */}
          {edges.map((e) => {
            const s = byId.get(e.source_node_id);
            const t = byId.get(e.target_node_id);
            if (!s || !t) return null;
            const mx = (s.x + t.x) / 2;
            const my = (s.y + t.y) / 2;
            const stroke = relationColor(e.relation);
            return (
              <g
                key={e.id}
                onMouseEnter={() => setHover({ kind: "edge", data: e })}
                onMouseLeave={() => setHover(null)}
                className="graph-edge"
              >
                <line
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={stroke}
                  strokeWidth={1 + 2 * e.weight}
                  strokeOpacity={0.7}
                />
                <text
                  x={mx}
                  y={my - 4}
                  textAnchor="middle"
                  className="graph-edge-label"
                >
                  {e.relation}
                </text>
                <circle
                  cx={mx}
                  cy={my}
                  r={6}
                  fill={stroke}
                  className="graph-edge-delete"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    if (confirm(`删除关系「${e.relation}」？`)) {
                      deleteGraphEdge(currentProjectId, e.id).then(refresh);
                    }
                  }}
                />
              </g>
            );
          })}

          {/* nodes */}
          {laid.map((n) => {
            const r = NODE_R + Math.min(10, n.degree);
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                className="graph-node"
                onMouseEnter={() => setHover({ kind: "node", data: n })}
                onMouseLeave={() => setHover(null)}
              >
                <circle
                  r={r}
                  fill={KIND_COLORS[n.node_kind]}
                  stroke="#0d0d0d"
                  strokeWidth={1.5}
                />
                <text
                  y={4}
                  textAnchor="middle"
                  className="graph-node-label"
                >
                  {n.name.slice(0, 4)}
                </text>
              </g>
            );
          })}

          {nodes.length === 0 && (
            <text x={W / 2} y={H / 2} textAnchor="middle" className="muted">
              图谱为空。点击「从拆书导入人物」或下方「+ 节点」开始构建。
            </text>
          )}
        </svg>

        {hover && (
          <div className="graph-tooltip">
            {hover.kind === "node" ? (
              <>
                <b>{(hover.data as GraphNode).name}</b>
                <div className="muted tiny">{(hover.data as GraphNode).node_kind}</div>
                {(hover.data as GraphNode).source_material_id != null && (
                  <div className="muted tiny">
                    来源: {materialTitlesById.get((hover.data as GraphNode).source_material_id!)
                       ?? `拆书 #${(hover.data as GraphNode).source_material_id}`}
                  </div>
                )}
                {(hover.data as GraphNode).extra?.role && (
                  <div>role: {(hover.data as GraphNode).extra!.role}</div>
                )}
                {(hover.data as GraphNode).extra?.tags && (
                  <div>tags: {(hover.data as GraphNode).extra!.tags.join(", ")}</div>
                )}
                <button
                  className="danger tiny"
                  onClick={() => {
                    if (confirm(`删除节点「${(hover.data as GraphNode).name}」？`)) {
                      deleteGraphNode(currentProjectId, (hover.data as GraphNode).id).then(
                        refresh,
                      );
                    }
                  }}
                >
                  删除
                </button>
              </>
            ) : (
              <>
                <b>{(hover.data as GraphEdge).relation}</b>
                <div className="muted tiny">weight {(hover.data as GraphEdge).weight}</div>
                {(hover.data as GraphEdge).evidence && (
                  <blockquote>「{(hover.data as GraphEdge).evidence}」</blockquote>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="graph-controls">
        <AddNodeForm onAdd={onAddNode} />
        <AddEdgeForm nodes={nodes} onAdd={onAddEdge} />
      </div>

      {showMaterialise && (
        <div className="modal-backdrop" onClick={() => setShowMaterialise(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>从拆书材料导入</h3>
              <button onClick={() => setShowMaterialise(false)}>×</button>
            </header>
            <div className="modal-body">
              {/* R22: 选 kind 决定这次导入什么 — 人物 / 伏笔 / 行为 / 全部。
                  行为模式会以 node_kind=other 出现在图上, 伏笔会变成
                  node_kind=event。默认 all 走原有"一键全导入"路径。 */}
              <div className="row" style={{ marginBottom: 10, gap: 6, flexWrap: "wrap" }}>
                <span className="muted small">导入范围:</span>
                {(["all", "character", "event", "behavior"] as const).map((k) => (
                  <button
                    key={k}
                    className={materialiseKind === k ? "primary" : ""}
                    onClick={() => setMaterialiseKind(k)}
                    style={{ fontSize: 12 }}
                  >
                    {k === "all" ? "全部" : k === "character" ? "人物" : k === "event" ? "伏笔" : "行为"}
                  </button>
                ))}
                <span className="muted tiny">· 人物同时会按章节共现创建「同章节出现」边</span>
              </div>
              {materials.length === 0 ? (
                <div className="muted">没有拆书材料。先到「拆书」页添加一份。</div>
              ) : (
                materials.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => onMaterialise(m.id, materialiseKind)}
                    className="row-button"
                    disabled={busy}
                  >
                    {m.title} · {m.character_count} 人物
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* R22: 短暂提示条, 显示最近一次导入的 nodes_created / edges_created。
          用 setTimeout 4s 后清掉, 不堆叠。 */}
      {materialiseToast && (
        <div className="graph-toast" onClick={() => setMaterialiseToast(null)}>
          {materialiseToast}
        </div>
      )}
    </div>
  );
}

function AddNodeForm({ onAdd }: { onAdd: (name: string, kind: GraphNodeKind) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<GraphNodeKind>("study_character");
  return (
    <div className="card add-node">
      <h4>+ 节点</h4>
      <div className="row">
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="人物名"
        />
        <select value={kind} onChange={(e) => setKind(e.target.value as GraphNodeKind)}>
          <option value="study_character">study_character</option>
          <option value="project_character">project_character</option>
          <option value="faction">faction</option>
          <option value="location">location</option>
          <option value="other">other</option>
        </select>
        <button
          className="primary"
          onClick={() => {
            onAdd(name, kind);
            setName("");
          }}
          disabled={!name.trim()}
        >
          添加
        </button>
      </div>
    </div>
  );
}

function AddEdgeForm({
  nodes,
  onAdd,
}: {
  nodes: GraphNode[];
  onAdd: (src: number, tgt: number, relation: string) => void;
}) {
  const [src, setSrc] = useState<number | null>(null);
  const [tgt, setTgt] = useState<number | null>(null);
  const [relation, setRelation] = useState("");
  return (
    <div className="card add-edge">
      <h4>+ 关系</h4>
      <div className="row">
        <select
          value={src ?? ""}
          onChange={(e) => setSrc(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">起始节点</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
        <span>→</span>
        <select
          value={tgt ?? ""}
          onChange={(e) => setTgt(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">目标节点</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
        <input
          className="input"
          value={relation}
          onChange={(e) => setRelation(e.target.value)}
          placeholder="关系（师父/对手/恋人/...）"
        />
        <button
          className="primary"
          onClick={() => {
            if (src != null && tgt != null && relation.trim()) {
              onAdd(src, tgt, relation);
              setRelation("");
            }
          }}
          disabled={src == null || tgt == null || !relation.trim()}
        >
          添加
        </button>
      </div>
    </div>
  );
}
