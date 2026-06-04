/**
 * GraphPage — R24 神经网络式 + 角色聚焦
 *
 * 改造点 (用户 R23 反馈):
 *   1. 神经网络感 — 节点有渐变 + 外发光, 边有半透明, 背景深色加点阵,
 *      力导向布局让节点按拓扑聚类
 *   2. 单角色聚焦 — 双击节点进入「focus」模式, 只看该节点 + 1 跳邻居
 *   3. 多选视图 — shift+点 累积选中, 「只看选中」模式只看节点 + 边
 *   4. 关系类型多样性 — 后端 R24 enrich 端点用 LLM 抽真实语义关系
 *      (师父/对手/恋人/...), 不再是「同章节出现」默认
 *
 * 物理模拟 (force-directed):
 *   - 库仑斥力: F = k_q / r^2, 全节点对
 *   - 胡克弹力: F = k_s * (r - rest_len), 仅边
 *   - 阻尼: v *= 0.85
 *   - 跑 ~300 步或到能量阈值
 *
 * 力导向的状态用 useState 触发不了 (每帧 setState 会卡) — 改用
 * useRef 存"当前迭代"位置 + forceUpdate 触发 re-render, ~30fps。
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
  enrichStudyRelationships,
} from "../api";
import type {
  GraphEdge,
  GraphNode,
  GraphNodeKind,
  StudyMaterial,
  MaterialiseSummary,
  StudyRelationshipEnrichedItem,
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

// 关系类型配色 (R24 新增, 之前只支持默认灰)
const RELATION_COLORS: Record<string, string> = {
  师父: "#d6a64e",
  弟子: "#d6a64e",
  师徒: "#d6a64e",
  对手: "#ef6b5b",
  仇人: "#a83232",
  恋人: "#e58fcf",
  夫妻: "#e58fcf",
  朋友: "#78c77a",
  同门: "#78c77a",
  家人: "#7fb3d5",
  兄弟: "#7fb3d5",
  姐妹: "#7fb3d5",
  父子: "#7fb3d5",
  母子: "#7fb3d5",
  主仆: "#b58863",
  势力: "#c19ad6",
  同盟: "#5dc9c9",
  合作: "#5dc9c9",
  敌人: "#a83232",
  同章节出现: "#5a82a6",
  default: "#888",
};

function relationColor(rel: string): string {
  return RELATION_COLORS[rel] ?? RELATION_COLORS.default;
}

const NODE_R = 22;
const VIEW_W = 1200;
const VIEW_H = 700;

type Pos = { x: number; y: number; vx: number; vy: number };
type LayedOut = GraphNode & { x: number; y: number; degree: number };
type Transform = { x: number; y: number; k: number };

// ---------- Force-directed 物理 -------------------------------------

/**
 * 跑 N 次迭代的力导向布局, 原地修改 pos。
 *
 * 物理参数: 库仑斥力 + 胡克弹力 + 中心引力 + 阻尼。
 * 撞墙: 边界 box 反弹, 不让节点飞出 viewBox。
 *
 * 之所以是同步函数: 我们在 useEffect 里跑完整 300 步, 然后 setState
 * 触发一次 re-render。中间帧不更新 React 树 — 否则 30fps setState
 * 会卡死大图 (50+ 节点)。
 */
function runForceLayout(
  pos: Map<number, Pos>,
  edges: GraphEdge[],
  nodeIds: number[],
  iterations: number = 300,
): void {
  if (nodeIds.length === 0) return;
  const cx = VIEW_W / 2;
  const cy = VIEW_H / 2;

  // 预计算度
  const degree = new Map<number, number>();
  edges.forEach((e) => {
    degree.set(e.source_node_id, (degree.get(e.source_node_id) ?? 0) + 1);
    degree.set(e.target_node_id, (degree.get(e.target_node_id) ?? 0) + 1);
  });

  // 物理常量 (手调到对 30-50 节点图好看)
  const REPULSION = 4500;        // 库仑 k
  const SPRING_K = 0.04;          // 胡克 k
  const SPRING_REST = 90;          // 边的"自然长度"
  const CENTER_PULL = 0.012;      // 向中心引力
  const DAMPING = 0.82;           // 速度阻尼
  const MAX_V = 18;               // 速度上限, 防止发散

  // 缓存 edge 端点 (避免循环里重复 read)
  const edgePairs: Array<[number, number]> = edges.map((e) => [e.source_node_id, e.target_node_id]);

  for (let it = 0; it < iterations; it++) {
    // 清零加速度
    const ax = new Map<number, number>();
    const ay = new Map<number, number>();
    nodeIds.forEach((id) => { ax.set(id, 0); ay.set(id, 0); });

    // 1) 库仑斥力 (n^2, 50 节点是 2500 对, 还好)
    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const a = pos.get(nodeIds[i])!;
        const b = pos.get(nodeIds[j])!;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) d2 = 0.01;
        const d = Math.sqrt(d2);
        const f = REPULSION / d2;
        const fx = (dx / d) * f;
        const fy = (dy / d) * f;
        // 度大者更"重", 受力小 (符合连接多就该靠中心的感觉)
        const wa = 1.0 / (1 + (degree.get(nodeIds[i]) ?? 0) * 0.15);
        const wb = 1.0 / (1 + (degree.get(nodeIds[j]) ?? 0) * 0.15);
        ax.set(nodeIds[i], ax.get(nodeIds[i])! + fx * wa);
        ay.set(nodeIds[i], ay.get(nodeIds[i])! + fy * wa);
        ax.set(nodeIds[j], ax.get(nodeIds[j])! - fx * wb);
        ay.set(nodeIds[j], ay.get(nodeIds[j])! - fy * wb);
      }
    }

    // 2) 胡克弹力 (仅边)
    edgePairs.forEach(([srcId, tgtId]) => {
      const a = pos.get(srcId);
      const b = pos.get(tgtId);
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = SPRING_K * (d - SPRING_REST);
      const fx = (dx / d) * f;
      const fy = (dy / d) * f;
      ax.set(srcId, ax.get(srcId)! + fx);
      ay.set(srcId, ay.get(srcId)! + fy);
      ax.set(tgtId, ax.get(tgtId)! - fx);
      ay.set(tgtId, ay.get(tgtId)! - fy);
    });

    // 3) 中心引力
    nodeIds.forEach((id) => {
      const p = pos.get(id)!;
      ax.set(id, ax.get(id)! + (cx - p.x) * CENTER_PULL);
      ay.set(id, ay.get(id)! + (cy - p.y) * CENTER_PULL);
    });

    // 4) 更新速度 + 位置
    nodeIds.forEach((id) => {
      const p = pos.get(id)!;
      p.vx = (p.vx + ax.get(id)!) * DAMPING;
      p.vy = (p.vy + ay.get(id)!) * DAMPING;
      // 速度上限
      if (p.vx > MAX_V) p.vx = MAX_V;
      if (p.vx < -MAX_V) p.vx = -MAX_V;
      if (p.vy > MAX_V) p.vy = MAX_V;
      if (p.vy < -MAX_V) p.vy = -MAX_V;
      p.x += p.vx;
      p.y += p.vy;
      // 撞墙反弹
      const margin = 30;
      if (p.x < margin) { p.x = margin; p.vx *= -0.5; }
      if (p.x > VIEW_W - margin) { p.x = VIEW_W - margin; p.vx *= -0.5; }
      if (p.y < margin) { p.y = margin; p.vy *= -0.5; }
      if (p.y > VIEW_H - margin) { p.y = VIEW_H - margin; p.vy *= -0.5; }
    });
  }
}

/** 圆形初始布局 — 力导向还没收敛时的"看起来没那么烂"的占位。*/
function initCircleLayout(nodeIds: number[]): Map<number, Pos> {
  const cx = VIEW_W / 2;
  const cy = VIEW_H / 2;
  const radius = Math.min(VIEW_W, VIEW_H) * 0.32;
  const pos = new Map<number, Pos>();
  nodeIds.forEach((id, i) => {
    const angle = (i / Math.max(1, nodeIds.length)) * Math.PI * 2;
    // 加一点随机噪声, 避免对称死锁
    const jitter = 0.05;
    pos.set(id, {
      x: cx + Math.cos(angle) * radius + (Math.random() - 0.5) * radius * jitter,
      y: cy + Math.sin(angle) * radius + (Math.random() - 0.5) * radius * jitter,
      vx: 0, vy: 0,
    });
  });
  return pos;
}

// ---------- 简单社区检测 (Louvain-lite: connected components) -----

function detectCommunities(nodes: GraphNode[], edges: GraphEdge[]): Map<number, number> {
  const adj = new Map<number, Set<number>>();
  nodes.forEach((n) => adj.set(n.id, new Set()));
  edges.forEach((e) => {
    adj.get(e.source_node_id)?.add(e.target_node_id);
    adj.get(e.target_node_id)?.add(e.source_node_id);
  });
  const visited = new Set<number>();
  const community = new Map<number, number>();
  let cid = 0;
  for (const n of nodes) {
    if (visited.has(n.id)) continue;
    const queue = [n.id];
    while (queue.length > 0) {
      const cur = queue.shift()!;
      if (visited.has(cur)) continue;
      visited.add(cur);
      community.set(cur, cid);
      for (const nb of adj.get(cur) ?? []) {
        if (!visited.has(nb)) queue.push(nb);
      }
    }
    cid++;
  }
  return community;
}

const COMMUNITY_PALETTE = [
  "#6e9ecf", "#78c77a", "#d6a64e", "#c19ad6", "#e58fcf",
  "#5dc9c9", "#b58863", "#ef9b5b", "#7fb3d5", "#a8a4e6",
  "#9bc76d", "#d77b9c", "#88c4a8", "#c0a062", "#b083d6",
];

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

  // R24 交互状态
  const [transform, setTransform] = useState<Transform>({ x: 0, y: 0, k: 1 });
  // positions 用 ref 存 (避免 setState 触发 30fps re-render),
  // 跑完物理模拟后用 layoutVersion 触发 re-render
  const positionsRef = useRef<Map<number, Pos>>(new Map());
  const [layoutVersion, setLayoutVersion] = useState(0);
  // 选中的节点 id 集合 (R24: 支持多选, 之前只能单选)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectedEdgeId, setSelectedEdgeId] = useState<number | null>(null);
  // R24: 3 种 focus 模式:
  //  - "all": 全图
  //  - "single": 单角色聚焦 (双击或点聚焦按钮) — 只看该节点 + 1 跳邻居
  //  - "multi": 多选模式 — 只看选中节点 + 它们之间的边
  //  - "neighbors": 选中节点的 N 跳邻居 (R24 留个 hook, 现在 = single)
  const [focusMode, setFocusMode] = useState<"all" | "single" | "multi">("all");
  const [focusRoot, setFocusRoot] = useState<number | null>(null);
  const [kindFilter, setKindFilter] = useState<Set<GraphNodeKind>>(new Set());
  const [search, setSearch] = useState("");
  const [edgeFromId, setEdgeFromId] = useState<number | null>(null);
  const [edgeRelation, setEdgeRelation] = useState("");
  const [edgeRelationPrompt, setEdgeRelationPrompt] = useState<{ fromId: number; toId: number } | null>(null);
  // R24: LLM 关系抽取进度 / 状态
  const [enrichBusy, setEnrichBusy] = useState(false);
  const [enrichToast, setEnrichToast] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<
    | { type: "pan"; startX: number; startY: number; baseX: number; baseY: number }
    | { type: "node"; nodeId: number; startX: number; startY: number; baseNodeX: number; baseNodeY: number }
    | null
  >(null);
  const [, forceTick] = useState(0);

  // ---------- 数据加载 --------------------------------------------------

  const refresh = async () => {
    if (currentProjectId == null) return;
    setBusy(true);
    try {
      const g = await getGraph(currentProjectId);
      const ns = g?.nodes ?? [];
      const es = g?.edges ?? [];
      setNodes(ns);
      setEdges(es);
      // 初始化 positions (新节点圆环, 老节点保留之前位置)
      const ids = ns.map((n) => n.id);
      const pos = positionsRef.current;
      const newPos = new Map<number, Pos>();
      const seed = initCircleLayout(ids);
      ids.forEach((id) => {
        const existing = pos.get(id);
        if (existing) {
          newPos.set(id, existing);
        } else {
          newPos.set(id, seed.get(id)!);
        }
      });
      positionsRef.current = newPos;
      // 异步跑力导向 (不阻塞 UI, 用 setTimeout 让首帧先画)
      setTimeout(() => {
        runForceLayout(newPos, es, ids, 300);
        setLayoutVersion((v) => v + 1);
      }, 50);
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

  useEffect(() => {
    if (!enrichToast) return;
    const t = setTimeout(() => setEnrichToast(null), 6000);
    return () => clearTimeout(t);
  }, [enrichToast]);

  // ---------- 派生状态 --------------------------------------------------

  // 节点的"计算后位置" — 把 ref 里的 Pos 拍平到 laid 里
  const laid = useMemo(() => {
    const pos = positionsRef.current;
    const degree = new Map<number, number>();
    edges.forEach((e) => {
      degree.set(e.source_node_id, (degree.get(e.source_node_id) ?? 0) + 1);
      degree.set(e.target_node_id, (degree.get(e.target_node_id) ?? 0) + 1);
    });
    return nodes.map((n) => {
      const p = pos.get(n.id);
      return {
        ...n,
        x: p?.x ?? VIEW_W / 2,
        y: p?.y ?? VIEW_H / 2,
        degree: degree.get(n.id) ?? 0,
      };
    });
    // layoutVersion 是 trigger, ref 改了它就 +1
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layoutVersion]);

  const byId = useMemo(() => {
    const m = new Map<number, LayedOut>();
    laid.forEach((n) => m.set(n.id, n));
    return m;
  }, [laid]);

  // 社区 — 节点着色 + 布局
  const community = useMemo(() => detectCommunities(nodes, edges), [nodes, edges]);
  // 给每个 kind 一个基础色, 社区色叠加 alpha (视觉上既反映类型又反映拓扑)
  const nodeColor = (n: LayedOut): string => {
    if (kindFilter.size > 0 && !kindFilter.has(n.node_kind)) return "#333";
    const cid = community.get(n.id) ?? 0;
    return COMMUNITY_PALETTE[cid % COMMUNITY_PALETTE.length];
  };

  // ---------- focus 模式: 算出要显示的节点 / 边 -------------------

  // "all" 模式: 全部; "single": 选中的 + 1 跳邻居; "multi": selectedIds
  // 都要再过 kindFilter
  const visibleNodeIds = useMemo(() => {
    let base: Set<number>;
    if (focusMode === "single" && focusRoot != null) {
      base = new Set<number>([focusRoot]);
      edges.forEach((e) => {
        if (e.source_node_id === focusRoot) base.add(e.target_node_id);
        if (e.target_node_id === focusRoot) base.add(e.source_node_id);
      });
    } else if (focusMode === "multi") {
      base = new Set<number>(selectedIds);
      // 多选时, 也包含选中节点之间的 1 跳路径 (用户看关系时常用)
      selectedIds.forEach((sid) => {
        edges.forEach((e) => {
          if (e.source_node_id === sid && selectedIds.has(e.target_node_id)) base.add(e.target_node_id);
          if (e.target_node_id === sid && selectedIds.has(e.source_node_id)) base.add(e.source_node_id);
        });
      });
    } else {
      base = new Set<number>(nodes.map((n) => n.id));
    }
    // 应用 kind filter
    if (kindFilter.size > 0) {
      const filtered = new Set<number>();
      base.forEach((id) => {
        const n = byId.get(id);
        if (n && kindFilter.has(n.node_kind)) filtered.add(id);
      });
      return filtered;
    }
    return base;
  }, [focusMode, focusRoot, selectedIds, nodes, edges, kindFilter, byId]);

  const visibleEdges = useMemo(
    () => edges.filter(
      (e) => visibleNodeIds.has(e.source_node_id) && visibleNodeIds.has(e.target_node_id),
    ),
    [edges, visibleNodeIds],
  );

  // 选中态: dim 不在 selectedIds (且不在 focus 范围内的) 节点
  const dimmedNodeIds = useMemo(() => {
    if (selectedIds.size === 0 && selectedEdgeId == null) return new Set<number>();
    const dim = new Set<number>();
    visibleNodeIds.forEach((id) => {
      // 选中的节点 / 邻居 / focus root 不 dim
      if (selectedIds.has(id)) return;
      if (focusMode === "single" && id === focusRoot) return;
      // 其它都 dim (简化逻辑, 避免 N^2 邻居展开)
      dim.add(id);
    });
    return dim;
  }, [selectedIds, selectedEdgeId, visibleNodeIds, focusMode, focusRoot]);

  const dimmedEdgeIds = useMemo(() => {
    if (selectedIds.size === 0 && selectedEdgeId == null) return new Set<number>();
    const dim = new Set<number>();
    visibleEdges.forEach((e) => {
      // 选中的边不 dim
      if (selectedEdgeId === e.id) return;
      // 边的两个端点都在 selectedIds 内不 dim
      if (selectedIds.has(e.source_node_id) && selectedIds.has(e.target_node_id)) return;
      // 单选时, 端点是 focus root 不 dim
      if (focusMode === "single" && (e.source_node_id === focusRoot || e.target_node_id === focusRoot)) return;
      dim.add(e.id);
    });
    return dim;
  }, [visibleEdges, selectedIds, selectedEdgeId, focusMode, focusRoot]);

  // 搜索命中
  const searchHits = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return new Set<number>();
    return new Set(nodes.filter((n) => n.name.toLowerCase().includes(q)).map((n) => n.id));
  }, [search, nodes]);

  // ---------- 缩放 / 平移 / 拖动 ---------------------------------------

  const clientToViewBox = useCallback((clientX: number, clientY: number): Pos => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0, vx: 0, vy: 0 };
    const svgX = ((clientX - rect.left) / rect.width) * VIEW_W;
    const svgY = ((clientY - rect.top) / rect.height) * VIEW_H;
    const vbX = (svgX - transform.x) / transform.k;
    const vbY = (svgY - transform.y) / transform.k;
    return { x: vbX, y: vbY, vx: 0, vy: 0 };
  }, [transform]);

  const handleWheel = useCallback((ev: React.WheelEvent<SVGSVGElement>) => {
    ev.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const svgX = ((ev.clientX - rect.left) / rect.width) * VIEW_W;
    const svgY = ((ev.clientY - rect.top) / rect.height) * VIEW_H;
    const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
    setTransform((t) => {
      const newK = Math.max(0.2, Math.min(4, t.k * factor));
      return {
        x: t.x - svgX * (newK - t.k),
        y: t.y - svgY * (newK - t.k),
        k: newK,
      };
    });
  }, []);

  const handleSvgPointerDown = (ev: React.PointerEvent<SVGSVGElement>) => {
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
      // 多选逻辑: shift+点 = 加选, 否则清空后单选
      if (ev.shiftKey) {
        setSelectedIds((prev) => {
          const next = new Set(prev);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        });
        setFocusMode("multi");
      } else {
        setSelectedIds(new Set([id]));
        setFocusMode("all");
      }
      setSelectedEdgeId(null);
      return;
    }
    // 空白处 — 平移 + 清选
    ev.stopPropagation();
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    dragRef.current = {
      type: "pan",
      startX: ev.clientX, startY: ev.clientY,
      baseX: transform.x, baseY: transform.y,
    };
    if (!ev.shiftKey) {
      setSelectedIds(new Set());
      setSelectedEdgeId(null);
      setFocusMode("all");
    }
  };

  const handleSvgPointerMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.type === "pan") {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      const dxSvg = ((ev.clientX - drag.startX) / rect.width) * VIEW_W;
      const dySvg = ((ev.clientY - drag.startY) / rect.height) * VIEW_H;
      setTransform((t) => ({ ...t, x: drag.baseX + dxSvg, y: drag.baseY + dySvg }));
    } else if (drag.type === "node") {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      const dxVb = ((ev.clientX - drag.startX) / rect.width) * VIEW_W / transform.k;
      const dyVb = ((ev.clientY - drag.startY) / rect.height) * VIEW_H / transform.k;
      const pos = positionsRef.current;
      const p = pos.get(drag.nodeId);
      if (p) {
        p.x = drag.baseNodeX + dxVb;
        p.y = drag.baseNodeY + dyVb;
        p.vx = 0; p.vy = 0;  // 拖动时冻结物理
        forceTick((v) => v + 1);
      }
    }
  };

  const handleSvgPointerUp = () => {
    dragRef.current = null;
  };

  const handleNodeDoubleClick = (nodeId: number) => {
    // 双击 = 进入 single focus 模式, 只看该节点 + 1 跳邻居
    setFocusMode("single");
    setFocusRoot(nodeId);
    setSelectedIds(new Set([nodeId]));
    setSelectedEdgeId(null);
    // 自动聚焦: zoom 1.5x, 节点居中
    const n = byId.get(nodeId);
    if (n) {
      const targetK = 1.5;
      setTransform({ x: VIEW_W / 2 - n.x * targetK, y: VIEW_H / 2 - n.y * targetK, k: targetK });
    }
  };

  const handleNodeClick = (nodeId: number, ev: React.MouseEvent) => {
    if (edgeFromId != null) {
      if (edgeFromId !== nodeId) {
        setEdgeRelationPrompt({ fromId: edgeFromId, toId: nodeId });
      }
      setEdgeFromId(null);
      return;
    }
    // 单击 (不是 shift) 由 pointer down 处理, 这里只处理 shift 的累加
    if (ev.shiftKey) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(nodeId)) next.delete(nodeId);
        else next.add(nodeId);
        return next;
      });
      setFocusMode("multi");
    }
  };

  const handleEdgeClick = (edgeId: number, ev: React.MouseEvent) => {
    ev.stopPropagation();
    setSelectedEdgeId(edgeId);
    setSelectedIds(new Set());
  };

  // ---------- 缩放控制 --------------------------------------------------

  const zoomBy = (factor: number) => {
    setTransform((t) => {
      const rect = svgRef.current?.getBoundingClientRect();
      const cx = rect ? rect.width / 2 : VIEW_W / 2;
      const cy = rect ? rect.height / 2 : VIEW_H / 2;
      const svgX = (cx / (rect?.width ?? VIEW_W)) * VIEW_W;
      const svgY = (cy / (rect?.height ?? VIEW_H)) * VIEW_H;
      const newK = Math.max(0.2, Math.min(4, t.k * factor));
      return { x: t.x - svgX * (newK - t.k), y: t.y - svgY * (newK - t.k), k: newK };
    });
  };

  const resetView = () => setTransform({ x: 0, y: 0, k: 1 });

  const fitAll = () => {
    if (laid.length === 0) { resetView(); return; }
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
    const cw = rect?.width ?? VIEW_W;
    const ch = rect?.height ?? VIEW_H;
    const k = Math.min(cw / w, ch / h) * 0.9;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    setTransform({ x: VIEW_W / 2 - cx * k, y: VIEW_H / 2 - cy * k, k });
  };

  const focusOnNode = (nodeId: number) => {
    const n = byId.get(nodeId);
    if (!n) return;
    const targetK = 1.5;
    setTransform({ x: VIEW_W / 2 - n.x * targetK, y: VIEW_H / 2 - n.y * targetK, k: targetK });
    setSelectedIds(new Set([nodeId]));
    setSelectedEdgeId(null);
    setFocusMode("all");
  };

  const resetLayout = () => {
    const ids = nodes.map((n) => n.id);
    const seed = initCircleLayout(ids);
    positionsRef.current = seed;
    setTimeout(() => {
      runForceLayout(seed, edges, ids, 300);
      setLayoutVersion((v) => v + 1);
    }, 50);
    setTransform({ x: 0, y: 0, k: 1 });
    setFocusMode("all");
    setFocusRoot(null);
    setSelectedIds(new Set());
  };

  // ---------- R24: LLM 关系抽取 ---------------------------------------

  const onEnrichRelationships = async () => {
    if (materials.length === 0) {
      setEnrichToast("没有拆书材料,先到「拆书」页添加一份");
      return;
    }
    // 选第一份有 character 的材料
    const mat = materials.find((m) => m.character_count > 0) ?? materials[0];
    setEnrichBusy(true);
    setEnrichToast(`正在跑 LLM 抽关系 (材料: 《${mat.title}》, 最多 30 对)…`);
    try {
      const r: any = await enrichStudyRelationships(mat.id, {
        max_pairs: 30,
        min_co_chapter_count: 1,
      });
      const data = r?.data;
      if (!data || !data.items) {
        setEnrichToast("抽取返回空");
        return;
      }
      // 把抽出来的关系作为"建议"用 — 不直接覆盖 graph_edges, 留给
      // 用户在图上点开边的 prompt 选 relation 时填充。弹一个 summary
      // toast + 在 enrichToast 里放一份"前 5 对示例"提示。
      const samples = (data.items as StudyRelationshipEnrichedItem[])
        .filter((it) => it.llm_inferred)
        .slice(0, 5)
        .map((it) => `${it.char_a_name}↔${it.char_b_name} ${it.relation}`)
        .join("  ·  ");
      setEnrichToast(
        `抽取完成 ${data.duration_ms}ms $${(data.cost_usd || 0).toFixed(3)} · ` +
        `${data.enriched_count} 条语义关系 / ${data.fallback_count} 兜底 / ${data.skipped_count} 跳过\n` +
        (samples || "(本次没有 LLM 抽出的语义关系)"),
      );
      // 应用到图: 遍历 enriched items, 对 (a, b) 间已存在的边, 把
      // relation 字段替换成 LLM 给的; 不存在的边先不创建 (用户没
      // 选就写库太重)。
      const inferredMap = new Map<string, string>();
      data.items.forEach((it: StudyRelationshipEnrichedItem) => {
        if (it.llm_inferred && it.confidence >= 0.5) {
          inferredMap.set(`${it.char_a_id}-${it.char_b_id}`, it.relation);
        }
      });
      setEdges((prev) =>
        prev.map((e) => {
          const k1 = `${e.source_node_id}-${e.target_node_id}`;
          const k2 = `${e.target_node_id}-${e.source_node_id}`;
          const rel = inferredMap.get(k1) ?? inferredMap.get(k2);
          return rel ? { ...e, relation: rel } : e;
        }),
      );
    } catch (e: any) {
      setEnrichToast(`抽取失败: ${e?.message ?? e}`);
    } finally {
      setEnrichBusy(false);
    }
  };

  // ---------- 杂项 handler --------------------------------------------

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

  // ---------- 渲染 -----------------------------------------------------

  if (currentProjectId == null) {
    return (
      <div className="page graph-page">
        <div className="empty">请先在左侧选中一个项目。</div>
      </div>
    );
  }

  return (
    <div className="page graph-page graph-neural">
      <header className="page-header">
        <h2>人物关系图谱</h2>
        <span className="muted">
          {visibleNodeIds.size}/{nodes.length} 节点 · {visibleEdges.length}/{edges.length} 关系
          {focusMode !== "all" && (
            <span className="focus-pill">
              {focusMode === "single" && focusRoot != null ? (
                <>聚焦: {byId.get(focusRoot)?.name} <button className="link" onClick={() => { setFocusMode("all"); setFocusRoot(null); }}>退出</button></>
              ) : (
                <>多选: {selectedIds.size} 个 <button className="link" onClick={() => { setFocusMode("all"); setSelectedIds(new Set()); }}>退出</button></>
              )}
            </span>
          )}
        </span>
        <span className="spacer" />
        <button onClick={onEnrichRelationships} disabled={enrichBusy} title="跑 LLM 把 R22 的「同章节出现」升级成真实语义关系">
          {enrichBusy ? "抽取中…" : "🧠 智能抽关系"}
        </button>
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
              style={{ borderColor: active ? c : undefined }}
            >
              <span className="legend-dot" style={{ background: c }} />
              {KIND_LABELS[k as GraphNodeKind] ?? k}
            </button>
          );
        })}
        {kindFilter.size > 0 && (
          <button className="legend-clear" onClick={() => setKindFilter(new Set())}>清除</button>
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
            if (e.key === "Enter" && searchHits.size > 0) focusOnNode([...searchHits][0]);
          }}
        />
        {search && (
          <span className="muted tiny">
            命中 {searchHits.size}
            <span className="graph-search-jump">
              {Array.from(searchHits).slice(0, 5).map((id) => (
                <button key={id} className="link" onClick={() => focusOnNode(id)}>
                  {byId.get(id)?.name}
                </button>
              ))}
            </span>
          </span>
        )}
        <span className="spacer" />
        <span className="muted tiny">{Math.round(transform.k * 100)}%</span>
        <button onClick={() => zoomBy(1.2)}>+</button>
        <button onClick={() => zoomBy(1 / 1.2)}>−</button>
        <button onClick={fitAll} title="适应窗口">⤢</button>
        <button onClick={resetView}>⏺</button>
        <button onClick={resetLayout} title="重置布局">↻</button>
      </div>

      {/* P0-OCCLUSION-1 v4: hint 从 canvas-wrap 内部浮层改成普通
       * 提示行, 放在 toolbar 跟 canvas 之间, position: static, 不
       * 覆盖任何区域. 之前 v1-v3 都假设 hint 是 canvas 内部绝对
       * 定位 (top/left: 8px), 但 css 里两套 .graph-hint 规则在抢
       * 定位, 实际渲染时 hint 会覆盖到 canvas 之外的左侧区, 视觉
       * 上像"深色大块遮住左侧". 改成静态流式元素后, hint 自身只
       * 占据 toolbar 下方一行, 不再跟 canvas 的 z-index/bg 打架. */}
      <div className="graph-hint muted tiny">
        🖱️ 滚轮缩放 · 拖背景平移 · 拖节点移动 · 点节点选中 · <b>shift+点</b> 多选 · <b>双击</b> 聚焦该角色
      </div>

      <div className="graph-canvas-wrap" ref={containerRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className={`graph-svg ${edgeFromId != null ? "edge-mode" : ""}`}
          preserveAspectRatio="xMidYMid meet"
          onWheel={handleWheel}
          onPointerDown={handleSvgPointerDown}
          onPointerMove={handleSvgPointerMove}
          onPointerUp={handleSvgPointerUp}
        >
          <defs>
            {/* R24: 节点渐变 — 给每个 kind 准备一个 radial gradient,
                这是"神经网络感"的关键 (中心亮, 边缘暗) */}
            {Object.entries(KIND_COLORS).map(([k, c]) => (
              <radialGradient key={k} id={`grad-${k}`} cx="40%" cy="40%" r="60%">
                <stop offset="0%" stopColor={c} stopOpacity="1" />
                <stop offset="100%" stopColor={c} stopOpacity="0.5" />
              </radialGradient>
            ))}
          </defs>

          <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
            {/* edges */}
            {visibleEdges.map((e) => {
              const s = byId.get(e.source_node_id);
              const t = byId.get(e.target_node_id);
              if (!s || !t) return null;
              const isSelected = selectedEdgeId === e.id;
              const isDimmed = dimmedEdgeIds.has(e.id);
              const stroke = relationColor(e.relation);
              return (
                <g
                  key={e.id}
                  className={`graph-edge ${isSelected ? "selected" : ""} ${isDimmed ? "dimmed" : ""}`}
                  onClick={(ev) => handleEdgeClick(e.id, ev)}
                >
                  <line
                    x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                    stroke={stroke}
                    strokeWidth={(1 + 2 * e.weight) * (isSelected ? 1.5 : 1)}
                    strokeOpacity={isDimmed ? 0.08 : 0.55}
                  />
                </g>
              );
            })}

            {/* edge labels (只在 selected / hover 端点之一时显示) */}
            {visibleEdges.map((e) => {
              const s = byId.get(e.source_node_id);
              const t = byId.get(e.target_node_id);
              if (!s || !t) return null;
              if (e.relation === "同章节出现") return null;  // 兜底标签不显示, 太乱
              const isSelected = selectedEdgeId === e.id;
              const isDimmed = dimmedEdgeIds.has(e.id);
              if (!isSelected && (selectedIds.size === 0 || isDimmed)) return null;
              const mx = (s.x + t.x) / 2;
              const my = (s.y + t.y) / 2;
              return (
                <text
                  key={`lbl-${e.id}`}
                  x={mx} y={my} dy="0.32em"
                  textAnchor="middle"
                  className={`graph-edge-label ${isSelected ? "selected" : ""}`}
                >
                  {e.relation}
                </text>
              );
            })}

            {/* nodes */}
            {laid.map((n) => {
              if (!visibleNodeIds.has(n.id)) return null;
              const r = NODE_R + Math.min(10, n.degree);
              const isSelected = selectedIds.has(n.id);
              const isDimmed = dimmedNodeIds.has(n.id);
              const isSearchHit = searchHits.has(n.id);
              const isFocusRoot = focusMode === "single" && focusRoot === n.id;
              const color = nodeColor(n);
              return (
                <g
                  key={n.id}
                  data-node-id={n.id}
                  transform={`translate(${n.x}, ${n.y})`}
                  className={`graph-node ${isSelected ? "selected" : ""} ${isDimmed ? "dimmed" : ""} ${isSearchHit ? "search-hit" : ""} ${isFocusRoot ? "focus-root" : ""} ${edgeFromId === n.id ? "edge-source" : ""}`}
                  onClick={(ev) => handleNodeClick(n.id, ev)}
                  onDoubleClick={() => handleNodeDoubleClick(n.id)}
                >
                  {/* 外发光 (neural 感的关键) */}
                  {(isSelected || isFocusRoot) && (
                    <circle r={r + 8} fill={color} opacity={0.18} className="graph-node-glow" />
                  )}
                  <circle
                    r={r}
                    fill={`url(#grad-${n.node_kind})`}
                    stroke={isSelected || isFocusRoot ? "#d6a64e" : "rgba(255,255,255,0.25)"}
                    strokeWidth={isSelected || isFocusRoot ? 2.5 : 1}
                  />
                  <text y={4} textAnchor="middle" className="graph-node-label">
                    {n.name.length > 4 ? n.name.slice(0, 4) + "…" : n.name}
                  </text>
                  {n.degree > 0 && (
                    <text x={r * 0.7} y={-r * 0.7} textAnchor="middle" className="graph-node-degree">
                      {n.degree}
                    </text>
                  )}
                </g>
              );
            })}

            {nodes.length === 0 && (
              <text x={VIEW_W / 2} y={VIEW_H / 2} textAnchor="middle" className="muted">
                图谱为空。点击「从拆书导入」或下方「+ 节点」开始构建。
              </text>
            )}
          </g>
        </svg>

        {edgeRelationPrompt && (
          <div className="graph-prompt">
            <div className="muted small">
              {byId.get(edgeRelationPrompt.fromId)?.name} → {byId.get(edgeRelationPrompt.toId)?.name}
            </div>
            <input
              autoFocus
              className="input"
              placeholder="关系名 (师父 / 对手 / 恋人 / 朋友 / 家人 / 仇人 / 兄弟 / ...)"
              value={edgeRelation}
              onChange={(e) => setEdgeRelation(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onConfirmEdgePrompt();
                if (e.key === "Escape") { setEdgeRelationPrompt(null); setEdgeRelation(""); }
              }}
            />
            <div className="row">
              <button onClick={onConfirmEdgePrompt} className="primary" disabled={!edgeRelation.trim()}>创建</button>
              <button onClick={() => { setEdgeRelationPrompt(null); setEdgeRelation(""); }}>取消</button>
            </div>
          </div>
        )}

        {enrichToast && (
          <div className="graph-enrich-toast" onClick={() => setEnrichToast(null)}>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{enrichToast}</pre>
          </div>
        )}
      </div>

      <div className="graph-controls">
        <AddNodeForm onAdd={onAddNode} />
        <AddEdgeForm nodes={nodes} onAdd={onAddEdge} />
      </div>

      {/* 选中详情侧栏 (R24: 多选时显示汇总) */}
      {selectedIds.size === 1 && (() => {
        const id = [...selectedIds][0];
        const node = byId.get(id);
        return node ? (
          <NodeDetailPanel
            key={id}
            node={node}
            edges={edges}
            byId={byId}
            materialTitlesById={materialTitlesById}
            onAddEdge={() => { setEdgeFromId(node.id); setSelectedIds(new Set()); setSelectedEdgeId(null); }}
            onFocus={() => handleNodeDoubleClick(node.id)}
            onDeleteNode={async () => {
              if (!confirm(`删除节点「${node.name}」？`)) return;
              await deleteGraphNode(currentProjectId, node.id);
              setSelectedIds(new Set());
              setSelectedEdgeId(null);
              await refresh();
            }}
            onSelectNode={(nid) => {
              setSelectedIds(new Set([nid]));
              setSelectedEdgeId(null);
            }}
            onClose={() => { setSelectedIds(new Set()); setSelectedEdgeId(null); }}
          />
        ) : null;
      })()}

      {selectedIds.size > 1 && (
        <MultiSelectPanel
          nodeIds={[...selectedIds]}
          nodes={byId}
          edges={edges}
          onFocusOne={(id) => handleNodeDoubleClick(id)}
          onClear={() => { setSelectedIds(new Set()); }}
          onDeleteAll={async () => {
            if (!confirm(`删除 ${selectedIds.size} 个节点?`)) return;
            for (const id of selectedIds) {
              await deleteGraphNode(currentProjectId, id);
            }
            setSelectedIds(new Set());
            await refresh();
          }}
        />
      )}

      {selectedEdgeId != null && (() => {
        const edge = edges.find((e) => e.id === selectedEdgeId);
        return edge ? (
          <EdgeDetailPanel
            key={edge.id}
            edge={edge}
            byId={byId}
            onDeleteEdge={async () => {
              if (!confirm(`删除关系「${edge.relation}」？`)) return;
              await deleteGraphEdge(currentProjectId, edge.id);
              setSelectedEdgeId(null);
              await refresh();
            }}
            onClose={() => setSelectedEdgeId(null)}
          />
        ) : null;
      })()}

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

      <EscListener onEsc={() => {
        if (edgeFromId != null) setEdgeFromId(null);
        else if (edgeRelationPrompt != null) { setEdgeRelationPrompt(null); setEdgeRelation(""); }
        else if (focusMode !== "all") { setFocusMode("all"); setFocusRoot(null); }
        else if (selectedIds.size > 0 || selectedEdgeId != null) {
          setSelectedIds(new Set()); setSelectedEdgeId(null);
        }
      }} />
    </div>
  );
}

// ---------- 详情侧栏 -----------------------------------------------------

function NodeDetailPanel({
  node, edges, byId, materialTitlesById, onAddEdge, onFocus, onDeleteNode, onSelectNode, onClose,
}: {
  node: LayedOut;
  edges: GraphEdge[];
  byId: Map<number, LayedOut>;
  materialTitlesById: Map<number, string>;
  onAddEdge: () => void;
  onFocus: () => void;
  onDeleteNode: () => void;
  onSelectNode: (id: number) => void;
  onClose: () => void;
}) {
  const myEdges = edges.filter(
    (e) => e.source_node_id === node.id || e.target_node_id === node.id,
  );
  // 按关系类型分组
  const edgesByRelation = myEdges.reduce<Record<string, GraphEdge[]>>((acc, e) => {
    (acc[e.relation] ??= []).push(e);
    return acc;
  }, {});
  return (
    <aside className="graph-side-panel">
      <header>
        <h3>{node.name}</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </header>
      <div className="muted small">
        {KIND_LABELS[node.node_kind] ?? node.node_kind} · 度数 {node.degree} · 社区 #{((byId.get(node.id) as any)?.community ?? 0) + 1}
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
        <button onClick={onFocus} className="primary small" title="双击节点也进入此模式">🎯 聚焦此角色</button>
        <button onClick={onAddEdge} className="small">+ 关系</button>
        <button onClick={onDeleteNode} className="danger small">删除</button>
      </div>
      <h4>关系 ({myEdges.length})</h4>
      {Object.keys(edgesByRelation).length === 0 ? (
        <div className="muted small">无</div>
      ) : (
        <ul className="side-edge-list">
          {Object.entries(edgesByRelation)
            .sort((a, b) => b[1].length - a[1].length)
            .map(([rel, es]) => (
              <li key={rel}>
                <b style={{ color: relationColor(rel) }}>{rel}</b>
                <span className="muted tiny"> × {es.length}</span>
                <ul style={{ listStyle: "none", padding: 0, margin: "2px 0 6px 8px" }}>
                  {es.map((e) => {
                    const isOut = e.source_node_id === node.id;
                    const otherId = isOut ? e.target_node_id : e.source_node_id;
                    const other = byId.get(otherId);
                    return (
                      <li key={e.id}>
                        <button className="link" onClick={() => onSelectNode(otherId)}>
                          {isOut ? "→" : "←"} {other?.name ?? `#${otherId}`}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
        </ul>
      )}
    </aside>
  );
}

function MultiSelectPanel({
  nodeIds, nodes, edges, onFocusOne, onClear, onDeleteAll,
}: {
  nodeIds: number[];
  nodes: Map<number, LayedOut>;
  edges: GraphEdge[];
  onFocusOne: (id: number) => void;
  onClear: () => void;
  onDeleteAll: () => void;
}) {
  // 选中节点之间的"内部边" — 体现多选目的
  const inner = edges.filter(
    (e) => nodeIds.includes(e.source_node_id) && nodeIds.includes(e.target_node_id),
  );
  return (
    <aside className="graph-side-panel">
      <header>
        <h3>已选 {nodeIds.length} 个角色</h3>
        <button onClick={onClear} className="close-btn">×</button>
      </header>
      <div className="muted small">
        内部关系: {inner.length} 条 (在选中节点之间)
      </div>
      <div className="side-actions">
        <button onClick={onDeleteAll} className="danger small">全部删除</button>
      </div>
      <h4>节点</h4>
      <ul className="side-edge-list">
        {nodeIds.map((id) => {
          const n = nodes.get(id);
          return (
            <li key={id}>
              <b>{n?.name ?? `#${id}`}</b>
              <span className="muted tiny"> 度 {n?.degree ?? 0}</span>
              <button className="link tiny" onClick={() => onFocusOne(id)}>🎯 聚焦</button>
            </li>
          );
        })}
      </ul>
      <h4>内部关系</h4>
      {inner.length === 0 ? (
        <div className="muted small">这些节点之间没有直接边</div>
      ) : (
        <ul className="side-edge-list">
          {inner.map((e) => {
            const a = nodes.get(e.source_node_id);
            const b = nodes.get(e.target_node_id);
            return (
              <li key={e.id}>
                {a?.name} <span style={{ color: relationColor(e.relation) }}><b>{e.relation}</b></span> {b?.name}
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
        <h3 style={{ color: relationColor(edge.relation) }}>{edge.relation}</h3>
        <button onClick={onClose} className="close-btn">×</button>
      </header>
      <div className="muted small">
        {src?.name ?? `#${edge.source_node_id}`} → {tgt?.name ?? `#${edge.target_node_id}`}
      </div>
      <div className="muted tiny">weight {edge.weight.toFixed(2)}</div>
      {edge.evidence && <blockquote className="quote">「{edge.evidence}」</blockquote>}
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
          className="input" value={name} onChange={(e) => setName(e.target.value)}
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
          className="primary" disabled={!name.trim()}
          onClick={() => { onAdd(name, kind); setName(""); }}
        >添加</button>
      </div>
    </div>
  );
}

function AddEdgeForm({
  nodes, onAdd,
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
        <select value={src ?? ""} onChange={(e) => setSrc(e.target.value ? Number(e.target.value) : null)}>
          <option value="">起始节点</option>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <span>→</span>
        <select value={tgt ?? ""} onChange={(e) => setTgt(e.target.value ? Number(e.target.value) : null)}>
          <option value="">目标节点</option>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
        <input
          className="input" value={relation} onChange={(e) => setRelation(e.target.value)}
          placeholder="关系 (师父/对手/恋人/...)"
        />
        <button
          className="primary"
          disabled={src == null || tgt == null || !relation.trim()}
          onClick={() => { if (src != null && tgt != null && relation.trim()) { onAdd(src, tgt, relation); setRelation(""); } }}
        >添加</button>
      </div>
    </div>
  );
}

function EscListener({ onEsc }: { onEsc: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onEsc(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onEsc]);
  return null;
}
