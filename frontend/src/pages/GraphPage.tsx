/**
 * GraphPage — R23 交互式图谱
 *
 * 关键交互 (R23 新增):
 *   1. Pan & Zoom    — 滚轮缩放(以光标为中心) + 背景拖动平移
 *   2. 拖拽节点      — 单节点可自由拖动; 拖动后位置会话内保持
 *   3. 点击选中      — 点节点 / 边高亮, 关联节点和边全亮, 其余暗化
 *   4. 类型过滤      — chip 多选 人物/伏笔/行为/其它, 选中后过滤图
 *   5. 搜索定位      — 顶部搜索框按 name 模糊匹配, 命中后 zoom 到节点
 *   6. 缩放控制      — 右上角小工具条: +/-/100%/适应窗口/重置布局
 *   7. 选中详情侧栏  — 右侧 slide-in 卡片, 显示节点的 extra/来源/关系
 *
 * 实现要点:
 *   - 节点位置存 React state (会话内有效); 重新 refresh 会触发
 *     layoutNodes 重新铺一次, 拖过的节点会回弹 — 这是 trade-off
 *     留给未来"把 layout 也存 backend"时再升级
 *   - pan/zoom 用一个 <g transform="translate(tx,ty) scale(k)">
 *     包住所有元素, 不动 viewBox
 *   - 用 pointer events 统一处理鼠标 + 触摸
 *   - 选中态用 CSS class (`.selected`, `.dimmed`) 控制透明度
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const KIND_LABELS: Record<GraphNodeKind, string> = {
  study_character: "拆书人物",
  project_character: "项目人物",
  faction: "势力",
  location: "地点",
  other: "其它",
};

const RELATION_COLORS: Record<string, string> = {
  师父: "#d6a64e",
  弟子: "#d6a64e",
  对手: "#ef6b5b",
  恋人: "#e58fcf",
  朋友: "#78c77a",
  仇人: "#a83232",
  势力: "#c19ad6",
  同章节出现: "#5a82a6",
  default: "#888",
};

function relationColor(rel: string): string {
  return RELATION_COLORS[rel] ?? RELATION_COLORS.default;
}

const NODE_R = 22;

type Pos = { x: number; y: number };
type LayedOut = GraphNode & { x: number; y: number; degree: number };
type Transform = { x: number; y: number; k: number };

// ---------- Layout (seeded circle) -------------------------------------

function layoutNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
): LayedOut[] {
  if (nodes.length === 0) return [];
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

// ---------- Component --------------------------------------------------

export function GraphPage() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [busy, setBusy] = useState(false);
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [showMaterialise, setShowMaterialise] = useState(false);
  const [materialiseKind, setMaterialiseKind] = useState<"all" | "character" | "event" | "behavior">("all");
  const [materialiseToast, setMaterialiseToast] = useState<string | null>(null);

  // R23: 交互状态
  // - transform: 全局 pan/zoom
  // - positions: 每个节点拖动后的位置 (overrides layoutNodes 的默认位置)
  // - selectedId: 当前选中的节点 / 边 id
  // - kindFilter: 类型过滤 (空集 = 全显示)
  // - search: 搜索框文字 (命中即高亮 + 自动滚到节点)
  // - edgeFromId: "从这个节点起手画关系" — 点节点的 "+关系" 按钮进入
  //   这个模式, 然后点另一个节点完成边的创建
  const [transform, setTransform] = useState<Transform>({ x: 0, y: 0, k: 1 });
  const [positions, setPositions] = useState<Record<number, Pos>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedKind, setSelectedKind] = useState<"node" | "edge" | null>(null);
  const [kindFilter, setKindFilter] = useState<Set<GraphNodeKind>>(new Set());
  const [search, setSearch] = useState("");
  const [edgeFromId, setEdgeFromId] = useState<number | null>(null);
  const [edgeRelation, setEdgeRelation] = useState("");

  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  // 拖动 / 平移 / 画边的临时状态, 用 ref 避免 setState 触发整树重渲染
  const dragRef = useRef<
    | { type: "pan"; startX: number; startY: number; baseX: number; baseY: number }
    | { type: "node"; nodeId: number; startX: number; startY: number; baseNodeX: number; baseNodeY: number }
    | { type: "edge-from"; fromId: number; cursorX: number; cursorY: number }
    | null
  >(null);
  const [dragOverlay, setDragOverlay] = useState<
    | { type: "edge-from"; fromId: number; cursorX: number; cursorY: number }
    | null
  >(null);

  const W = 1200;
  const H = 700;

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

  useEffect(() => {
    if (!materialiseToast) return;
    const t = setTimeout(() => setMaterialiseToast(null), 4000);
    return () => clearTimeout(t);
  }, [materialiseToast]);

  // R23: 应用 kindFilter 后剩下的节点 — 过滤掉的节点连带它们
  // 涉及的边一起隐藏 (孤立边没意义, 视觉上只会乱)
  const visibleNodeIds = useMemo(() => {
    if (kindFilter.size === 0) return new Set(nodes.map((n) => n.id));
    return new Set(nodes.filter((n) => kindFilter.has(n.node_kind)).map((n) => n.id));
  }, [nodes, kindFilter]);
  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (e) => visibleNodeIds.has(e.source_node_id) && visibleNodeIds.has(e.target_node_id),
      ),
    [edges, visibleNodeIds],
  );

  // R23: 把 layoutNodes 算出来的位置跟用户拖动后的位置合并;
  // 拖动过 -> 用 positions, 否则 -> 用 layout 默认
  const laid = useMemo(() => {
    const defaultLaid = layoutNodes(nodes, visibleEdges, W, H);
    return defaultLaid.map((n) => {
      const p = positions[n.id];
      return p ? { ...n, x: p.x, y: p.y } : n;
    });
  }, [nodes, visibleEdges, positions]);

  const byId = useMemo(() => {
    const m = new Map<number, LayedOut>();
    laid.forEach((n) => m.set(n.id, n));
    return m;
  }, [laid]);

  // R23: 搜索高亮 — 在 laid 里匹配 name, 命中的节点亮黄边
  const searchHits = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return new Set<number>();
    return new Set(
      nodes
        .filter((n) => n.name.toLowerCase().includes(q))
        .map((n) => n.id),
    );
  }, [search, nodes]);

  // R23: 选中态决定"亮 / 暗"。如果选了一个节点, 它自己 + 跟它
  // 相连的边 / 节点保持原色, 其它暗化
  const dimmedIds = useMemo(() => {
    if (selectedKind !== "node" || selectedId == null) return new Set<number>();
    const connected = new Set<number>([selectedId]);
    edges.forEach((e) => {
      if (e.source_node_id === selectedId) connected.add(e.target_node_id);
      if (e.target_node_id === selectedId) connected.add(e.source_node_id);
    });
    const dim = new Set<number>();
    nodes.forEach((n) => {
      if (!connected.has(n.id)) dim.add(n.id);
    });
    return dim;
  }, [selectedKind, selectedId, edges, nodes]);

  const dimmedEdgeIds = useMemo(() => {
    if (selectedKind !== "node" || selectedId == null) return new Set<number>();
    const dim = new Set<number>();
    edges.forEach((e) => {
      if (e.source_node_id !== selectedId && e.target_node_id !== selectedId) {
        dim.add(e.id);
      }
    });
    return dim;
  }, [selectedKind, selectedId, edges]);

  // R23: 滚轮缩放 — 以光标位置为中心; 防止缩太小或太大
  const handleWheel = useCallback((ev: React.WheelEvent<SVGSVGElement>) => {
    ev.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    // 把 client 坐标 → svg viewBox 坐标
    const svgX = ((ev.clientX - rect.left) / rect.width) * W;
    const svgY = ((ev.clientY - rect.top) / rect.height) * H;
    const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
    setTransform((t) => {
      const newK = Math.max(0.2, Math.min(4, t.k * factor));
      // 让 viewBox 坐标 svgX 在屏幕上保持原位:
      // 旧: screenX = t.x + svgX * t.k
      // 新: 想要 newX + svgX * newK == 旧 screenX
      // → newX = t.x + svgX * t.k - svgX * newK = t.x - svgX * (newK - t.k)
      return {
        x: t.x - svgX * (newK - t.k),
        y: t.y - svgY * (newK - t.k),
        k: newK,
      };
    });
  }, []);

  // R23: 把客户端坐标 (clientX, clientY) 转成 viewBox 坐标
  // (考虑 transform 后的偏移和缩放)
  const clientToViewBox = useCallback(
    (clientX: number, clientY: number): Pos => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return { x: 0, y: 0 };
      // svg 坐标 (相对 svg 元素)
      const svgX = ((clientX - rect.left) / rect.width) * W;
      const svgY = ((clientY - rect.top) / rect.height) * H;
      // 转换回 viewBox 坐标 (考虑 transform: t.x + vbX * t.k = svgX)
      const vbX = (svgX - transform.x) / transform.k;
      const vbY = (svgY - transform.y) / transform.k;
      return { x: vbX, y: vbY };
    },
    [transform],
  );

  // R23: 节点拖动 / 背景平移 / 画边的 pointer 事件
  // 全部在 svg 上挂 onPointerDown, 根据 hit target 决定是哪种模式
  const handleSvgPointerDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    // 必须在 viewBox 坐标里 hit 一个节点才进入"拖节点"模式
    const target = ev.target as Element;
    const nodeG = target.closest("[data-node-id]");
    if (nodeG) {
      const id = Number(nodeG.getAttribute("data-node-id"));
      const node = byId.get(id);
      if (!node) return;
      ev.stopPropagation();
      (ev.target as Element).setPointerCapture?.(ev.pointerId);
      dragRef.current = {
        type: "node",
        nodeId: id,
        startX: ev.clientX,
        startY: ev.clientY,
        baseNodeX: node.x,
        baseNodeY: node.y,
      };
      setSelectedId(id);
      setSelectedKind("node");
      return;
    }
    // 否则进入背景平移模式
    ev.stopPropagation();
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    dragRef.current = {
      type: "pan",
      startX: ev.clientX,
      startY: ev.clientY,
      baseX: transform.x,
      baseY: transform.y,
    };
  };

  const handleSvgPointerMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.type === "pan") {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      // 像素位移 -> svg 坐标位移
      const dxSvg = ((ev.clientX - drag.startX) / rect.width) * W;
      const dySvg = ((ev.clientY - drag.startY) / rect.height) * H;
      setTransform((t) => ({ ...t, x: drag.baseX + dxSvg, y: drag.baseY + dySvg }));
    } else if (drag.type === "node") {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      const dxVb = ((ev.clientX - drag.startX) / rect.width) * W / transform.k;
      const dyVb = ((ev.clientY - drag.startY) / rect.height) * H / transform.k;
      setPositions((p) => ({
        ...p,
        [drag.nodeId]: { x: drag.baseNodeX + dxVb, y: drag.baseNodeY + dyVb },
      }));
    } else if (drag.type === "edge-from") {
      // 跟着光标画一条临时边
      const vb = clientToViewBox(ev.clientX, ev.clientY);
      setDragOverlay({ type: "edge-from", fromId: drag.fromId, cursorX: vb.x, cursorY: vb.y });
    }
  };

  const handleSvgPointerUp = (ev: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.type === "edge-from") {
      // 看光标下是不是另一个节点 — 命中则进入关系名输入
      const target = ev.target as Element;
      const nodeG = target.closest("[data-node-id]");
      if (nodeG) {
        const toId = Number(nodeG.getAttribute("data-node-id"));
        if (toId !== drag.fromId) {
          setEdgeRelationPrompt({ fromId: drag.fromId, toId });
        }
      }
      setDragOverlay(null);
    }
    dragRef.current = null;
  };

  // R23: "+关系" 模式 — 点完"+关系"按钮后, 下一次点任意节点就是 to
  const [edgeRelationPrompt, setEdgeRelationPrompt] = useState<{ fromId: number; toId: number } | null>(null);

  const handleNodeClick = (nodeId: number) => {
    if (edgeFromId != null) {
      if (edgeFromId !== nodeId) {
        setEdgeRelationPrompt({ fromId: edgeFromId, toId: nodeId });
      }
      setEdgeFromId(null);
      return;
    }
    setSelectedId(nodeId);
    setSelectedKind("node");
  };

  const handleEdgeClick = (edgeId: number) => {
    setSelectedId(edgeId);
    setSelectedKind("edge");
  };

  // R23: 缩放控制按钮
  const zoomBy = (factor: number) => {
    setTransform((t) => {
      const rect = svgRef.current?.getBoundingClientRect();
      const cx = rect ? rect.width / 2 : W / 2;
      const cy = rect ? rect.height / 2 : H / 2;
      const svgX = (cx / (rect?.width ?? W)) * W;
      const svgY = (cy / (rect?.height ?? H)) * H;
      const newK = Math.max(0.2, Math.min(4, t.k * factor));
      const newX = t.x - svgX * (newK - t.k);
      const newY = t.y - svgY * (newK - t.k);
      return { x: newX, y: newY, k: newK };
    });
  };

  const resetView = () => {
    setTransform({ x: 0, y: 0, k: 1 });
  };

  const fitAll = () => {
    if (laid.length === 0) {
      resetView();
      return;
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    laid.forEach((n) => {
      const r = NODE_R + Math.min(10, n.degree);
      minX = Math.min(minX, n.x - r);
      minY = Math.min(minY, n.y - r);
      maxX = Math.max(maxX, n.x + r);
      maxY = Math.max(maxY, n.y + r);
    });
    const w = maxX - minX;
    const h = maxY - minY;
    const rect = containerRef.current?.getBoundingClientRect();
    const cw = rect?.width ?? W;
    const ch = rect?.height ?? H;
    const k = Math.min(cw / w, ch / h) * 0.9;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    // viewBox 中心 (cx, cy) 应该映射到 svg 中心 (cw/2, ch/2)
    // svgX = t.x + cx * t.k → t.x = svgX - cx * t.k
    // svgX 占 viewBox 的比例 = svgX / W, 实际屏幕 = svgX * (cw / W)
    // 这里直接用 svg 中心在 viewBox 坐标中的位置: (cx, cy)
    // t.x + cx * t.k == W/2  →  t.x = W/2 - cx * t.k
    setTransform({ x: W / 2 - cx * k, y: H / 2 - cy * k, k });
  };

  // R23: 点击搜索框里命中节点的"定位"按钮 — zoom + pan 到它
  const focusOnNode = (nodeId: number) => {
    const n = byId.get(nodeId);
    if (!n) return;
    const targetK = 1.5;
    // 让节点 n 居中: t.x + n.x * t.k == W/2  →  t.x = W/2 - n.x * t.k
    setTransform({ x: W / 2 - n.x * targetK, y: H / 2 - n.y * targetK, k: targetK });
    setSelectedId(nodeId);
    setSelectedKind("node");
  };

  const resetLayout = () => {
    setPositions({});
    setTransform({ x: 0, y: 0, k: 1 });
  };

  // R23: 类型过滤 chip 切换
  const toggleKind = (k: GraphNodeKind) => {
    setKindFilter((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

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

  const onConfirmEdgePrompt = async () => {
    if (!edgeRelationPrompt || !edgeRelation.trim()) return;
    await onAddEdge(edgeRelationPrompt.fromId, edgeRelationPrompt.toId, edgeRelation);
    setEdgeRelationPrompt(null);
    setEdgeRelation("");
  };

  const onMaterialise = async (materialId: number, kind: "all" | "character" | "event" | "behavior") => {
    if (currentProjectId == null) return;
    setBusy(true);
    try {
      const r: any = await materialiseFromStudy(currentProjectId, materialId, kind, true);
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

  const materialTitlesById = useMemo(() => {
    const m = new Map<number, string>();
    for (const mat of materials) m.set(mat.id, mat.title);
    return m;
  }, [materials]);

  const relationsInUse = useMemo(() => {
    const s = new Set<string>();
    visibleEdges.forEach((e) => s.add(e.relation));
    return Array.from(s).sort();
  }, [visibleEdges]);

  const selectedNode = selectedKind === "node" && selectedId != null ? byId.get(selectedId) : null;
  const selectedEdge =
    selectedKind === "edge" && selectedId != null
      ? edges.find((e) => e.id === selectedId) ?? null
      : null;

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
          {laid.length}/{nodes.length} 节点 · {visibleEdges.length}/{edges.length} 关系
        </span>
        <span className="spacer" />
        <button onClick={() => setShowMaterialise(true)}>从拆书导入</button>
        <button onClick={refresh} disabled={busy}>
          {busy ? "刷新中…" : "刷新"}
        </button>
      </header>

      <div className="graph-legend">
        <span className="legend-title">类型过滤：</span>
        {Object.entries(KIND_COLORS).map(([k, c]) => {
          const active = kindFilter.size === 0 || kindFilter.has(k as GraphNodeKind);
          return (
            <button
              key={k}
              className={`legend-chip ${active ? "active" : ""}`}
              onClick={() => toggleKind(k as GraphNodeKind)}
              title={active ? "点击隐藏" : "点击只显示"}
            >
              <span className="legend-dot" style={{ background: c }} />
              {KIND_LABELS[k as GraphNodeKind] ?? k}
            </button>
          );
        })}
        {kindFilter.size > 0 && (
          <button className="legend-clear" onClick={() => setKindFilter(new Set())}>
            清除过滤
          </button>
        )}
        <span className="legend-title" style={{ marginLeft: 16 }}>关系：</span>
        {relationsInUse.length === 0 && <span className="muted tiny">（暂无）</span>}
        {relationsInUse.map((r) => (
          <span key={r} className="legend-item">
            <span className="legend-bar" style={{ background: relationColor(r) }} />
            {r}
          </span>
        ))}
      </div>

      <div className="graph-toolbar">
        <input
          className="input graph-search"
          placeholder="🔍 搜索节点名 (回车定位)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && searchHits.size > 0) {
              focusOnNode([...searchHits][0]);
            }
          }}
        />
        {search && (
          <span className="muted tiny">
            命中 {searchHits.size} 个
            {searchHits.size > 0 && (
              <span className="graph-search-jump">
                {Array.from(searchHits)
                  .slice(0, 5)
                  .map((id) => byId.get(id)?.name)
                  .filter(Boolean)
                  .map((name, i) => (
                    <button key={i} className="link" onClick={() => focusOnNode([...searchHits][i])}>
                      {name}
                    </button>
                  ))}
              </span>
            )}
          </span>
        )}
        <span className="spacer" />
        <span className="muted tiny">
          {Math.round(transform.k * 100)}%
        </span>
        <button onClick={() => zoomBy(1.2)} title="放大">+</button>
        <button onClick={() => zoomBy(1 / 1.2)} title="缩小">−</button>
        <button onClick={fitAll} title="适应窗口">⤢</button>
        <button onClick={resetView} title="100%">⏺</button>
        <button onClick={resetLayout} title="重置布局">↻</button>
      </div>

      <div className="graph-canvas-wrap" ref={containerRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className={`graph-svg ${edgeFromId != null ? "edge-mode" : ""}`}
          preserveAspectRatio="xMidYMid meet"
          onWheel={handleWheel}
          onPointerDown={handleSvgPointerDown}
          onPointerMove={handleSvgPointerMove}
          onPointerUp={handleSvgPointerUp}
        >
          <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
            {/* edges */}
            {visibleEdges.map((e) => {
              const s = byId.get(e.source_node_id);
              const t = byId.get(e.target_node_id);
              if (!s || !t) return null;
              const isSelected = selectedKind === "edge" && selectedId === e.id;
              const isDimmed = dimmedEdgeIds.has(e.id);
              const stroke = relationColor(e.relation);
              return (
                <g
                  key={e.id}
                  className={`graph-edge ${isSelected ? "selected" : ""} ${isDimmed ? "dimmed" : ""}`}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    handleEdgeClick(e.id);
                  }}
                >
                  <line
                    x1={s.x}
                    y1={s.y}
                    x2={t.x}
                    y2={t.y}
                    stroke={stroke}
                    strokeWidth={(1 + 2 * e.weight) * (isSelected ? 1.5 : 1)}
                    strokeOpacity={isDimmed ? 0.15 : 0.7}
                  />
                </g>
              );
            })}

            {/* edge labels — 总是显示, 但 dim 状态淡化; 选中态放大 */}
            {visibleEdges.map((e) => {
              const s = byId.get(e.source_node_id);
              const t = byId.get(e.target_node_id);
              if (!s || !t) return null;
              const mx = (s.x + t.x) / 2;
              const my = (s.y + t.y) / 2;
              const isDimmed = dimmedEdgeIds.has(e.id);
              const isSelected = selectedKind === "edge" && selectedId === e.id;
              return (
                <text
                  key={`lbl-${e.id}`}
                  x={mx}
                  y={my}
                  textAnchor="middle"
                  dy="0.32em"
                  className={`graph-edge-label ${isDimmed ? "dimmed" : ""} ${isSelected ? "selected" : ""}`}
                >
                  {e.relation}
                </text>
              );
            })}

            {/* drag-to-create-edge overlay (only when user has clicked "+关系") */}
            {dragOverlay && dragOverlay.type === "edge-from" && (() => {
              const from = byId.get(dragOverlay.fromId);
              if (!from) return null;
              return (
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={dragOverlay.cursorX}
                  y2={dragOverlay.cursorY}
                  stroke="var(--accent-gold, #d6a64e)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  strokeOpacity={0.9}
                  pointerEvents="none"
                />
              );
            })()}

            {/* nodes */}
            {laid.map((n) => {
              const r = NODE_R + Math.min(10, n.degree);
              const isSelected = selectedKind === "node" && selectedId === n.id;
              const isDimmed = dimmedIds.has(n.id);
              const isSearchHit = searchHits.has(n.id);
              return (
                <g
                  key={n.id}
                  data-node-id={n.id}
                  transform={`translate(${n.x}, ${n.y})`}
                  className={`graph-node ${isSelected ? "selected" : ""} ${isDimmed ? "dimmed" : ""} ${isSearchHit ? "search-hit" : ""} ${edgeFromId === n.id ? "edge-source" : ""}`}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    handleNodeClick(n.id);
                  }}
                >
                  <circle
                    r={r}
                    fill={KIND_COLORS[n.node_kind]}
                    stroke={isSelected ? "#d6a64e" : "#0d0d0d"}
                    strokeWidth={isSelected ? 3 : 1.5}
                  />
                  <text
                    y={4}
                    textAnchor="middle"
                    className="graph-node-label"
                  >
                    {n.name.length > 4 ? n.name.slice(0, 4) + "…" : n.name}
                  </text>
                  {/* degree 标签 (连接数), 小角标 */}
                  {n.degree > 0 && (
                    <text
                      x={r * 0.7}
                      y={-r * 0.7}
                      textAnchor="middle"
                      className="graph-node-degree"
                    >
                      {n.degree}
                    </text>
                  )}
                </g>
              );
            })}

            {/* empty state */}
            {nodes.length === 0 && (
              <text x={W / 2} y={H / 2} textAnchor="middle" className="muted">
                图谱为空。点击「从拆书导入」或下方「+ 节点」开始构建。
              </text>
            )}
          </g>
        </svg>

        {/* 缩放控制 + 提示 */}
        <div className="graph-hint muted tiny">
          {edgeFromId != null
            ? "🖱️ 点选目标节点完成「+关系」,Esc 取消"
            : "🖱️ 滚轮缩放 · 拖背景平移 · 拖节点移动 · 点节点选中"}
        </div>

        {/* 关系名输入 prompt — 在 edgeFromId 模式中点完第二个节点后弹出 */}
        {edgeRelationPrompt && (
          <div className="graph-prompt">
            <div className="muted small">
              {byId.get(edgeRelationPrompt.fromId)?.name} →{" "}
              {byId.get(edgeRelationPrompt.toId)?.name}
            </div>
            <input
              autoFocus
              className="input"
              placeholder="关系名 (师父 / 对手 / 恋人 / 同章节出现 / ...)"
              value={edgeRelation}
              onChange={(e) => setEdgeRelation(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onConfirmEdgePrompt();
                if (e.key === "Escape") {
                  setEdgeRelationPrompt(null);
                  setEdgeRelation("");
                }
              }}
            />
            <div className="row">
              <button onClick={onConfirmEdgePrompt} className="primary" disabled={!edgeRelation.trim()}>
                创建
              </button>
              <button
                onClick={() => {
                  setEdgeRelationPrompt(null);
                  setEdgeRelation("");
                }}
              >
                取消
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="graph-controls">
        <AddNodeForm onAdd={onAddNode} />
        <AddEdgeForm nodes={nodes} onAdd={onAddEdge} />
      </div>

      {/* 选中侧栏 */}
      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          edges={edges}
          byId={byId}
          materialTitlesById={materialTitlesById}
          onAddEdge={() => {
            setEdgeFromId(selectedNode.id);
            setSelectedId(null);
            setSelectedKind(null);
          }}
          onDeleteNode={async () => {
            if (!confirm(`删除节点「${selectedNode.name}」？`)) return;
            await deleteGraphNode(currentProjectId, selectedNode.id);
            setSelectedId(null);
            setSelectedKind(null);
            await refresh();
          }}
          onSelectNode={(id) => {
            setSelectedId(id);
            setSelectedKind("node");
          }}
          onClose={() => {
            setSelectedId(null);
            setSelectedKind(null);
          }}
        />
      )}

      {selectedEdge && (
        <EdgeDetailPanel
          edge={selectedEdge}
          byId={byId}
          onDeleteEdge={async () => {
            if (!confirm(`删除关系「${selectedEdge.relation}」？`)) return;
            await deleteGraphEdge(currentProjectId, selectedEdge.id);
            setSelectedId(null);
            setSelectedKind(null);
            await refresh();
          }}
          onClose={() => {
            setSelectedId(null);
            setSelectedKind(null);
          }}
        />
      )}

      {showMaterialise && (
        <div className="modal-backdrop" onClick={() => setShowMaterialise(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>从拆书材料导入</h3>
              <button onClick={() => setShowMaterialise(false)}>×</button>
            </header>
            <div className="modal-body">
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

      {materialiseToast && (
        <div className="graph-toast" onClick={() => setMaterialiseToast(null)}>
          {materialiseToast}
        </div>
      )}

      {/* Esc 取消 edgeFromId 模式 */}
      <EscListener onEsc={() => {
        if (edgeFromId != null) {
          setEdgeFromId(null);
        } else if (edgeRelationPrompt != null) {
          setEdgeRelationPrompt(null);
          setEdgeRelation("");
        } else if (selectedId != null) {
          setSelectedId(null);
          setSelectedKind(null);
        }
      }} />
    </div>
  );
}

// ---------- 详情侧栏 -----------------------------------------------------

function NodeDetailPanel({
  node, edges, byId, materialTitlesById, onAddEdge, onDeleteNode, onSelectNode, onClose,
}: {
  node: LayedOut;
  edges: GraphEdge[];
  byId: Map<number, LayedOut>;
  materialTitlesById: Map<number, string>;
  onAddEdge: () => void;
  onDeleteNode: () => void;
  onSelectNode: (id: number) => void;
  onClose: () => void;
}) {
  const myEdges = edges.filter(
    (e) => e.source_node_id === node.id || e.target_node_id === node.id,
  );
  return (
    <aside className="graph-side-panel">
      <header>
        <h3>{node.name}</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </header>
      <div className="muted small">
        {KIND_LABELS[node.node_kind] ?? node.node_kind} · 度数 {node.degree}
      </div>
      {node.source_material_id != null && (
        <div className="muted tiny">
          来源: {materialTitlesById.get(node.source_material_id) ?? `拆书 #${node.source_material_id}`}
        </div>
      )}
      {node.extra?.role && (
        <div className="side-row">
          <span className="muted tiny">角色:</span> {node.extra.role}
        </div>
      )}
      {node.extra?.tags && (node.extra.tags as string[]).length > 0 && (
        <div className="side-row">
          <span className="muted tiny">标签:</span>
          {(node.extra.tags as string[]).map((t) => (
            <span key={t} className="chip-mini">{t}</span>
          ))}
        </div>
      )}
      <div className="side-actions">
        <button onClick={onAddEdge} className="primary small">+ 关系</button>
        <button onClick={onDeleteNode} className="danger small">删除节点</button>
      </div>
      <h4>关系 ({myEdges.length})</h4>
      {myEdges.length === 0 ? (
        <div className="muted small">无</div>
      ) : (
        <ul className="side-edge-list">
          {myEdges.map((e) => {
            const isOut = e.source_node_id === node.id;
            const otherId = isOut ? e.target_node_id : e.source_node_id;
            const other = byId.get(otherId);
            return (
              <li key={e.id}>
                <button className="link" onClick={() => onSelectNode(otherId)}>
                  {other?.name ?? `#${otherId}`}
                </button>
                <span className="muted tiny">
                  {isOut ? "→" : "←"} {e.relation} (w={e.weight.toFixed(2)})
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

function EdgeDetailPanel({
  edge, byId, onDeleteEdge, onClose,
}: {
  edge: GraphEdge;
  byId: Map<number, LayedOut>;
  onDeleteEdge: () => void;
  onClose: () => void;
}) {
  const src = byId.get(edge.source_node_id);
  const tgt = byId.get(edge.target_node_id);
  return (
    <aside className="graph-side-panel">
      <header>
        <h3>{edge.relation}</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </header>
      <div className="muted small">
        {src?.name ?? `#${edge.source_node_id}`} → {tgt?.name ?? `#${edge.target_node_id}`}
      </div>
      <div className="muted tiny">weight {edge.weight.toFixed(2)}</div>
      {edge.evidence && (
        <blockquote className="quote">「{edge.evidence}」</blockquote>
      )}
      <div className="side-actions">
        <button onClick={onDeleteEdge} className="danger small">删除关系</button>
      </div>
    </aside>
  );
}

// ---------- 通用 --------------------------------------------------------

function AddNodeForm({ onAdd }: { onAdd: (name: string, kind: GraphNodeKind) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<GraphNodeKind>("project_character");
  return (
    <div className="card add-node">
      <h4>+ 节点</h4>
      <div className="row">
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="人物名 / 势力名 / 地点"
        />
        <select value={kind} onChange={(e) => setKind(e.target.value as GraphNodeKind)}>
          <option value="study_character">拆书人物</option>
          <option value="project_character">项目人物</option>
          <option value="faction">势力</option>
          <option value="location">地点</option>
          <option value="other">其它</option>
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
          placeholder="关系 (师父/对手/恋人/...)"
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

// Esc 监听 — 跟全局键盘配合
function EscListener({ onEsc }: { onEsc: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEsc();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onEsc]);
  return null;
}
