/**
 * MemoryShelfPage + MemoryArchivePage — 项目记忆库 (P3)
 *
 * P0 stub: 直接渲染旧 MemoryPage. P3 阶段 (04_P3) 改成三层:
 *
 *   第一层  /memory          项目记忆书架 (本文件) — 每项目一本记忆册
 *   第二层  /memory/:pid      记忆档案馆 (本文件) — 7 柜 + 讨论室
 *   第三层  (entity 点开)     单实体详情 (人物 / 物品 / 地点 / ...)
 *
 * P3 §2 命名:
 *   - 左侧导航: 知识库 → 记忆库 (P3 §2 强调"不再跟拆书知识库混淆")
 *   - 页面标题: 项目记忆库
 *   - 副标题  : "MemoryUpdate Agent 写入原始记忆,经 MemoryConsolidator
 *                二次加工后形成稳定项目档案。"
 *
 * P3 §5 核心原则: 冲突不单独暴露成冲突档案柜,直接进讨论室拿结果。
 * 前端只显示 DiscussionDecision 列表 (裁决中 / 待裁决 / 已裁决),不显示
 * 一堆冲突让用户手动处理 (P3 §14 禁 3).
 *
 * P3 §11 写流程: Planner / Draft / Continuity 只读 Stable*, 不读 raw.
 * 这是后端层强制的,前端看不到 raw → stable 直接关系。
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  listProjectMemoryShelf,
  getProjectMemoryArchive,
  consolidateProjectMemory,
  listProjectMemoryEntities,
  getProjectMemoryEntity,
  listProjectMemoryForeshadows,
  listProjectMemoryFacts,
  listDiscussionDecisions,
  runDiscussionDecision,
  applyDiscussionDecision,
  listRawMemoryEntries,
} from "../api";
import {
  CABINETS,
  DECISION_STATUS_LABEL,
  DECISION_TOPIC_TYPE_LABEL,
  type CabinetType,
  type ConsolidateResponse,
  type DiscussionDecision,
  type ProjectMemoryArchiveOverview,
  type ProjectMemoryShelfItem,
  type ProjectMemoryShelfResponse,
  type RawMemoryEntry,
  type StableMemoryEntity,
  type StableMemoryEntityDetail,
} from "../types";
import {
  ShelfLayout, ShelfRow, ShelfBook, ShelfToolbar,
  ShelfSidePanel, ShelfDetailPanel,
  type ShelfColorType,
} from "../components/shelf";
import { ShelfBreadcrumb } from "../components/shelf";
import { listProjects } from "../api";

// ============================================================
// 7 柜的视觉映射 — 跟 SHELF_COLORS 走
// ============================================================
const CABINET_COLOR: Record<CabinetType, ShelfColorType> = {
  character:   "blue",     // 人物主写
  location:    "green",    // 地点稳定
  faction:     "purple",   // 势力有冲突
  item:        "gold",     // 物品有剧情价值
  world_rule:  "gray",     // 世界规则硬骨架
  foreshadow:  "purple",   // 伏笔待推进
  hard_fact:   "gray",     // 硬事实归档
};

const CABINET_CONFIG: Record<CabinetType, { key: CabinetType; label: string; emoji: string }> = CABINETS.reduce(
  (acc, c) => {
    acc[c.key] = c;
    return acc;
  },
  {} as Record<CabinetType, { key: CabinetType; label: string; emoji: string }>,
);

// 记忆册健康度 → 颜色 (P3 §4 健康分)
function healthColor(score: number | null): ShelfColorType {
  if (score == null) return "gray";
  if (score >= 0.8) return "green";
  if (score >= 0.5) return "blue";
  if (score >= 0.2) return "purple";
  return "red";
}

// 7 柜总实体数
function totalEntities(it: ProjectMemoryShelfItem): number {
  return it.character_count + it.location_count + it.faction_count
       + it.item_count + it.world_rule_count
       + it.foreshadow_count + it.hard_fact_count;
}

// hover hint
function buildShelfHover(it: ProjectMemoryShelfItem): string {
  const total = totalEntities(it);
  const last = it.last_consolidated_at
    ? new Date(it.last_consolidated_at).toLocaleString("zh-CN")
    : "—";
  return [
    `项目: ${it.project_name}`,
    `健康分: ${it.health_score != null ? it.health_score.toFixed(2) : "—"}`,
    `稳定实体: ${total} (人物 ${it.character_count} · 地点 ${it.location_count} · 势力 ${it.faction_count} · 物品 ${it.item_count} · 规则 ${it.world_rule_count} · 伏笔 ${it.foreshadow_count} · 硬事实 ${it.hard_fact_count})`,
    `原始记忆: ${it.raw_entry_count} (待加工 ${it.raw_entry_pending})`,
    `待裁决: ${it.decision_pending} · 裁决中: ${it.decision_running}`,
    `最近加工: ${last}`,
  ].join("\n");
}

// ============================================================
// 第一层: 项目记忆书架
// ============================================================
export function MemoryShelfPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ProjectMemoryShelfResponse | null>(null);
  const [projectNames, setProjectNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 搜索: 按项目名 (中文输入, 简单 includes)
  const [search, setSearch] = useState("");
  // 类型过滤: "all" / "active" / "archived" / "trouble" (trouble = 任何 裁决>0)
  const [filter, setFilter] = useState<"all" | "active" | "archived" | "trouble">("all");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      setLoading(true);
      Promise.all([listProjectMemoryShelf(), listProjects().catch(() => [])])
        .then(([shelf, projects]) => {
          if (cancelled) return;
          setData(shelf);
          const map: Record<number, string> = {};
          (Array.isArray(projects) ? projects : []).forEach((p: any) => { map[p.id] = p.name; });
          setProjectNames(map);
          setErrorMsg(null);
          if (selectedId == null) {
            if (shelf.items.length > 0) setSelectedId(`project:${shelf.items[0].project_id}`);
            else if (shelf.system_books.length > 0) setSelectedId(`system:${shelf.system_books[0].key}`);
          }
        })
        .catch((e) => { if (!cancelled) setErrorMsg(String(e?.message ?? e)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    load();
    const h = window.setInterval(load, 10000);
    return () => { cancelled = true; window.clearInterval(h); };
    // selectedId 是 getter 不参与依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 过滤
  const filtered = useMemo(() => {
    if (!data) return { active: [], archived: [], trouble: [] };
    let items = data.items;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      items = items.filter((it) => it.project_name.toLowerCase().includes(q));
    }
    const active = items.filter((it) => it.status !== "archived");
    const archived = items.filter((it) => it.status === "archived");
    const trouble = items.filter((it) =>
      it.raw_entry_pending > 0 || it.decision_pending > 0 || it.decision_running > 0,
    );
    return { active, archived, trouble };
  }, [data, search]);

  // 汇总
  const summary = useMemo(() => {
    if (!data) return { projects: 0, total_entities: 0, raw_pending: 0, decisions_pending: 0, decisions_running: 0, health_avg: null as number | null };
    const items = data.items;
    const total_entities = items.reduce((s, it) => s + totalEntities(it), 0);
    const raw_pending = items.reduce((s, it) => s + it.raw_entry_pending, 0);
    const decisions_pending = items.reduce((s, it) => s + it.decision_pending, 0);
    const decisions_running = items.reduce((s, it) => s + it.decision_running, 0);
    const scored = items.filter((it) => it.health_score != null) as Array<ProjectMemoryShelfItem & { health_score: number }>;
    const health_avg = scored.length > 0
      ? scored.reduce((s, it) => s + (it.health_score ?? 0), 0) / scored.length
      : null;
    return { projects: items.length, total_entities, raw_pending, decisions_pending, decisions_running, health_avg };
  }, [data]);

  // 选中解析: "project:33" or "system:raw_pool"
  const selected = useMemo(() => {
    if (!data || !selectedId) return null;
    const [kind, idStr] = selectedId.split(":");
    if (kind === "project") {
      const it = data.items.find((x) => x.project_id === Number(idStr));
      return it ? { kind: "project" as const, item: it } : null;
    } else {
      const sb = data.system_books.find((x) => x.key === idStr);
      return sb ? { kind: "system" as const, item: sb } : null;
    }
  }, [data, selectedId]);

  // 触发 consolidate (P3 stub 真写, 但只是把 raw → processed, 没有真合并)
  const onConsolidate = async (projectId: number) => {
    try {
      setErrorMsg(`正在对项目 #${projectId} 跑二次加工 (P3 stub) ...`);
      const r: ConsolidateResponse = await consolidateProjectMemory(projectId, { batch_limit: 50, run_discussion_inline: true });
      setErrorMsg(`二次加工完成: processed=${r.processed} · merged=${r.merged} · rejected=${r.rejected} · needs_discussion=${r.needs_discussion} · duration=${r.duration_ms}ms (P3 stub: 真合并留 P3.1)`);
    } catch (e: any) {
      setErrorMsg(`二次加工失败: ${e?.message ?? e}`);
    }
  };

  return (
    <ShelfLayout
      title="项目记忆库"
      subtitle="MemoryUpdate Agent 写入原始记忆,经 MemoryConsolidator 二次加工后形成稳定项目档案。"
      breadcrumb={[{ label: "项目记忆库" }]}
      left={
        <>
          <ShelfToolbar>
            <input
              className="input"
              placeholder="🔍 搜索项目名"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="shelf-toolbar-chips">
              {([
                ["all",      `全部 (${data?.items.length ?? 0})`],
                ["active",   `写作中 (${filtered.active.length})`],
                ["trouble",  `待裁决 (${filtered.trouble.length})`],
                ["archived", `已归档 (${filtered.archived.length})`],
              ] as const).map(([k, label]) => (
                <button
                  key={k}
                  className={`shelf-toolbar-chip ${filter === k ? "active" : ""}`}
                  onClick={() => setFilter(k)}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              className="primary"
              onClick={() => navigate("/memory")}
              title="刷新当前页 (P3 stub 按钮,等同刷新)"
            >
              🔄 刷新
            </button>
          </ShelfToolbar>

          {errorMsg && (
            <ShelfSidePanel title="提示" accentColor="red">
              <div style={{ fontSize: 11, color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>{errorMsg}</div>
            </ShelfSidePanel>
          )}

          <ShelfSidePanel title="全库总览" accentColor="purple">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <Stat label="项目数" value={summary.projects} />
              <Stat label="稳定实体" value={summary.total_entities} />
              <Stat label="原始待加工" value={summary.raw_pending} />
              <Stat label="待裁决" value={summary.decisions_pending} />
              <Stat label="裁决中" value={summary.decisions_running} />
              <Stat
                label="平均健康"
                value={summary.health_avg != null ? summary.health_avg.toFixed(2) : "—"}
              />
            </div>
          </ShelfSidePanel>

          <ShelfSidePanel title="3 本系统维护册" accentColor="gray">
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
              {data?.system_books.map((sb) => (
                <button
                  key={sb.key}
                  className="shelf-toolbar-chip"
                  style={{ justifyContent: "flex-start", textAlign: "left" }}
                  onClick={() => setSelectedId(`system:${sb.key}`)}
                  title={sb.subtitle}
                >
                  <span style={{ fontWeight: 500 }}>{sb.label}</span>
                  <span style={{ color: "var(--text-muted)", marginLeft: 4, fontSize: 10 }}>· {sb.subtitle}</span>
                </button>
              ))}
            </div>
          </ShelfSidePanel>
        </>
      }
      center={
        <>
          {loading && !data ? (
            <div className="muted small" style={{ padding: 24 }}>加载项目记忆库…</div>
          ) : (data?.items.length ?? 0) === 0 ? (
            <div className="empty-large">
              <div className="empty-large-glyph">❖</div>
              <h3>项目记忆库还是空的</h3>
              <p>项目记忆库是项目级的稳定记忆 (7 档案柜 + 讨论裁决)。<br />
              先到 <a href="/projects">项目书架</a> 创建一个项目, 然后让 MemoryUpdate Agent 写入原始记忆, 二次加工后会在这里形成档案册。</p>
            </div>
          ) : (
            <>
              {filter !== "archived" && (
                <ShelfRow
                  title="📚 写作中的记忆册"
                  subtitle={`(${filtered.active.length} 本)`}
                  emptyHint="— 还没有正在写作的项目 —"
                >
                  {filtered.active.map((it) => (
                    <ShelfBook
                      key={it.project_id}
                      title={it.project_name}
                      subtitle={`稳定 ${totalEntities(it)} · 待裁决 ${it.decision_pending} · 健康 ${it.health_score != null ? it.health_score.toFixed(2) : "—"}`}
                      status={it.raw_entry_pending > 0 || it.decision_pending > 0 ? "待加工" : "稳定"}
                      progressPct={it.health_score != null ? Math.round(it.health_score * 100) : 0}
                      progressLabel={`稳定 ${totalEntities(it)} · 原始 ${it.raw_entry_count}`}
                      colorType={healthColor(it.health_score)}
                      selected={selectedId === `project:${it.project_id}`}
                      onClick={() => setSelectedId(`project:${it.project_id}`)}
                      hoverHint={buildShelfHover(it)}
                    />
                  ))}
                </ShelfRow>
              )}

              {filter !== "active" && filtered.trouble.length > 0 && (
                <ShelfRow
                  title="⚠ 待加工 / 待裁决"
                  subtitle={`(${filtered.trouble.length} 本)`}
                  emptyHint=""
                >
                  {filtered.trouble.map((it) => (
                    <ShelfBook
                      key={`trouble-${it.project_id}`}
                      title={it.project_name}
                      subtitle={`待加工 ${it.raw_entry_pending} · 待裁决 ${it.decision_pending}`}
                      status="待处理"
                      progressPct={it.raw_entry_pending > 0 ? 50 : 80}
                      progressLabel="点击处理"
                      colorType="red"
                      selected={selectedId === `project:${it.project_id}`}
                      onClick={() => setSelectedId(`project:${it.project_id}`)}
                      hoverHint={buildShelfHover(it)}
                    />
                  ))}
                </ShelfRow>
              )}

              {filter !== "active" && (
                <ShelfRow
                  title="🗄 已归档的记忆册"
                  subtitle={`(${filtered.archived.length} 本)`}
                  emptyHint="— 还没有归档的项目 —"
                >
                  {filtered.archived.map((it) => (
                    <ShelfBook
                      key={it.project_id}
                      title={it.project_name}
                      subtitle={`归档 · 稳定 ${totalEntities(it)}`}
                      status="归档"
                      colorType="gray"
                      selected={selectedId === `project:${it.project_id}`}
                      onClick={() => setSelectedId(`project:${it.project_id}`)}
                      hoverHint={buildShelfHover(it)}
                    />
                  ))}
                </ShelfRow>
              )}

              <ShelfRow
                title="🔧 系统维护册"
                subtitle="(3 本)"
                emptyHint=""
              >
                {data?.system_books.map((sb) => (
                  <ShelfBook
                    key={sb.key}
                    title={sb.label}
                    subtitle={sb.subtitle}
                    status="系统"
                    colorType="gray"
                    selected={selectedId === `system:${sb.key}`}
                    onClick={() => setSelectedId(`system:${sb.key}`)}
                  />
                ))}
              </ShelfRow>
            </>
          )}
        </>
      }
      right={
        <ShelfDetailPanel
          title={
            !selected ? "未选中记忆册" :
            selected.kind === "project" ? selected.item.project_name :
            selected.item.label
          }
          subtitle={
            !selected ? "点中间书架里的一本记忆册查看详情" :
            selected.kind === "project"
              ? `项目 #${selected.item.project_id} · 健康分 ${selected.item.health_score != null ? selected.item.health_score.toFixed(2) : "—"}`
              : selected.item.subtitle
          }
          accentColor={
            !selected ? "gray" :
            selected.kind === "project" ? healthColor(selected.item.health_score) :
            "gray"
          }
          stats={
            selected?.kind === "project" ? [
              { label: "人物", value: selected.item.character_count },
              { label: "地点", value: selected.item.location_count },
              { label: "势力", value: selected.item.faction_count },
              { label: "物品", value: selected.item.item_count },
              { label: "世界规则", value: selected.item.world_rule_count },
              { label: "伏笔", value: selected.item.foreshadow_count },
              { label: "硬事实", value: selected.item.hard_fact_count },
              { label: "原始记忆", value: selected.item.raw_entry_count },
            ] : []
          }
          actions={
            selected?.kind === "project" ? (
              <>
                <button
                  className="primary"
                  onClick={() => navigate(`/memory/${selected.item.project_id}`)}
                  title="进入第二层 — 7 柜档案馆"
                >
                  📖 打开档案馆
                </button>
                <button
                  onClick={() => onConsolidate(selected.item.project_id)}
                  disabled={selected.item.raw_entry_pending === 0}
                  title={selected.item.raw_entry_pending > 0
                    ? "把 raw 条目标成 processed (P3 stub: 没有真合并, 留 P3.1)"
                    : "没有 raw 待加工的条目"}
                >
                  🔄 触发 Consolidate ({selected.item.raw_entry_pending})
                </button>
                <button
                  onClick={() => navigate(`/memory/${selected.item.project_id}#decisions`)}
                  title="讨论裁决记录"
                >
                  💬 讨论室 ({selected.item.decision_pending + selected.item.decision_running})
                </button>
                <button
                  onClick={() => navigate(`/memory/${selected.item.project_id}#raw`)}
                  title="原始记忆池"
                >
                  📋 原始记忆 ({selected.item.raw_entry_count})
                </button>
              </>
            ) : selected?.kind === "system" ? (
              <SystemBookActions bookKey={selected.item.key} navigate={navigate} />
            ) : null
          }
        >
          {selected?.kind === "project" ? (
            <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: 4 }}>
              <div>状态: <b style={{ color: selected.item.status === "archived" ? "var(--text-muted)" : "var(--text-primary)" }}>{selected.item.status}</b></div>
              <div>最近加工: {selected.item.last_consolidated_at ? new Date(selected.item.last_consolidated_at).toLocaleString("zh-CN") : "—"}</div>
              <div>原始待加工: <b style={{ color: selected.item.raw_entry_pending > 0 ? "var(--accent-red, #c45858)" : "inherit" }}>{selected.item.raw_entry_pending}</b></div>
              <div>待裁决 / 裁决中: <b>{selected.item.decision_pending}</b> / <b>{selected.item.decision_running}</b></div>
              <div style={{ marginTop: 6, padding: 6, background: "var(--bg-elevated)", borderRadius: 3, fontSize: 10, lineHeight: 1.5 }}>
                <b>P3 §5 核心原则</b>: 冲突不单独暴露成冲突档案柜, 直接进讨论室拿结果。<br />
                <b>P3 §11 写流程</b>: Planner / Draft / Continuity 只读 Stable*, 读不到 raw。
              </div>
            </div>
          ) : selected?.kind === "system" ? (
            <SystemBookHint bookKey={selected.item.key} />
          ) : (
            <div className="muted small">点中间书架里的一本记忆册, 这里会显示该项目的 7 柜统计 + 健康分 + 操作按钮。</div>
          )}
        </ShelfDetailPanel>
      }
    />
  );
}

// 3 个系统维护册的快捷操作
function SystemBookActions({ bookKey, navigate }: { bookKey: string; navigate: ReturnType<typeof useNavigate> }) {
  if (bookKey === "raw_pool") {
    return (
      <button onClick={() => navigate("/projects")} title="所有项目的原始记忆汇总 (在每个项目档案馆下)">
        📋 查看项目列表
      </button>
    );
  }
  if (bookKey === "stable_index") {
    return (
      <button onClick={() => navigate("/projects")} title="稳定记忆是每个项目档案馆的 7 柜汇总">
        📚 查看项目列表
      </button>
    );
  }
  if (bookKey === "decisions") {
    return (
      <button onClick={() => navigate("/projects")} title="讨论裁决记录在每个项目档案馆下 #decisions">
        💬 进入项目讨论室
      </button>
    );
  }
  return null;
}
function SystemBookHint({ bookKey }: { bookKey: string }) {
  if (bookKey === "raw_pool") return <Hint body="MemoryUpdateAgent 写入的原始记忆池,经 Consolidator 二次加工后转 stable。所有 raw 永久保留 (P3 §14 禁 5),不删除。" />;
  if (bookKey === "stable_index") return <Hint body="去重 / 合并 / 冲突识别后的稳定记忆。7 柜 (人物/地点/势力/物品/世界规则/伏笔/硬事实) 走 StableMemoryEntity 一张表,按 entity_type 区分。" />;
  if (bookKey === "decisions") return <Hint body="Consolidator 不能自动决定时, 创建 DiscussionDecision, 走 DiscussionAgent 拿裁决结果。决策 apply 后写回 Stable。" />;
  return null;
}
function Hint({ body }: { body: string }) {
  return <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>{body}</div>;
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

// ============================================================
// 第二层: 记忆档案馆 — /memory/:projectId
// ============================================================
export function MemoryArchivePage() {
  const { projectId: pidStr } = useParams();
  const projectId = Number(pidStr);
  const navigate = useNavigate();

  const [overview, setOverview] = useState<ProjectMemoryArchiveOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeCabinet, setActiveCabinet] = useState<CabinetType | "decisions" | "raw">("character");
  const [entities, setEntities] = useState<StableMemoryEntity[]>([]);
  const [decisions, setDecisions] = useState<DiscussionDecision[]>([]);
  const [rawEntries, setRawEntries] = useState<RawMemoryEntry[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<StableMemoryEntityDetail | null>(null);
  const [search, setSearch] = useState("");

  // 拉概览
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoading(true);
    getProjectMemoryArchive(projectId)
      .then((o) => { if (!cancelled) setOverview(o); })
      .catch((e) => { if (!cancelled) setErrorMsg(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  // 拉当前 cabinet 内容
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setSelectedEntity(null);
    if (activeCabinet === "decisions") {
      listDiscussionDecisions(projectId, { limit: 200 })
        .then((d) => { if (!cancelled) setDecisions(d); })
        .catch(() => { if (!cancelled) setDecisions([]); });
      return () => { cancelled = true; };
    }
    if (activeCabinet === "raw") {
      listRawMemoryEntries(projectId, { limit: 200 })
        .then((d) => { if (!cancelled) setRawEntries(d); })
        .catch(() => { if (!cancelled) setRawEntries([]); });
      return () => { cancelled = true; };
    }
    if (activeCabinet === "foreshadow") {
      listProjectMemoryForeshadows(projectId, { limit: 200 })
        .then((d) => { if (!cancelled) setEntities(d); })
        .catch(() => { if (!cancelled) setEntities([]); });
    } else if (activeCabinet === "hard_fact") {
      listProjectMemoryFacts(projectId, { limit: 200 })
        .then((d) => { if (!cancelled) setEntities(d); })
        .catch(() => { if (!cancelled) setEntities([]); });
    } else {
      listProjectMemoryEntities(projectId, { type: activeCabinet, limit: 200 })
        .then((d) => { if (!cancelled) setEntities(d); })
        .catch(() => { if (!cancelled) setEntities([]); });
    }
    return () => { cancelled = true; };
  }, [projectId, activeCabinet]);

  // 哈希 → 初始 tab
  useEffect(() => {
    if (window.location.hash === "#decisions") setActiveCabinet("decisions");
    else if (window.location.hash === "#raw") setActiveCabinet("raw");
  }, []);

  // 过滤
  const filteredEntities = useMemo(() => {
    if (!search.trim()) return entities;
    const q = search.trim().toLowerCase();
    return entities.filter((e) =>
      e.canonical_name.toLowerCase().includes(q)
      || e.aliases.some((a) => a.toLowerCase().includes(q))
      || e.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [entities, search]);

  // 选中实体详情
  const onSelectEntity = async (entityId: number) => {
    try {
      const d = await getProjectMemoryEntity(projectId, entityId);
      setSelectedEntity(d);
    } catch (e: any) {
      setErrorMsg(String(e?.message ?? e));
    }
  };

  // 跑讨论
  const onRunDecision = async (decId: number) => {
    try {
      setErrorMsg(`正在对 decision #${decId} 跑 DiscussionAgent (P3 stub) ...`);
      const r = await runDiscussionDecision(projectId, decId, { max_turns: 2 });
      setErrorMsg(`Decision #${decId} 已裁决: ${r.decision} — ${r.reason ?? ""}`);
      // 刷新当前 tab
      setActiveCabinet("decisions");
    } catch (e: any) {
      setErrorMsg(`讨论失败: ${e?.message ?? e}`);
    }
  };

  // 应用裁决
  const onApplyDecision = async (decId: number) => {
    try {
      setErrorMsg(`正在 apply decision #${decId} ...`);
      const r = await applyDiscussionDecision(projectId, decId, {});
      setErrorMsg(`Apply 完成: ${r.message} · 影响 ${r.affected_entity_ids.length} 个实体, ${r.created_timeline_event_ids.length} 条 timeline`);
      setActiveCabinet("decisions");
    } catch (e: any) {
      setErrorMsg(`Apply 失败: ${e?.message ?? e}`);
    }
  };

  if (!projectId) {
    return (
      <div className="page-empty">
        <ShelfBreadcrumb
          backTo="/memory"
          backLabel="返回项目记忆库"
          items={[{ label: "记忆档案馆" }]}
        />
        <p className="muted">缺少 projectId 参数。</p>
      </div>
    );
  }

  if (loading && !overview) {
    return (
      <div className="page-body">
        <ShelfBreadcrumb
          backTo="/memory"
          backLabel="返回项目记忆库"
          items={[{ label: `记忆档案 #${projectId}` }]}
        />
        <div className="muted small" style={{ padding: 24 }}>加载档案馆…</div>
      </div>
    );
  }

  if (errorMsg && !overview) {
    return (
      <div className="page-body">
        <ShelfBreadcrumb
          backTo="/memory"
          backLabel="返回项目记忆库"
          items={[{ label: `记忆档案 #${projectId}` }]}
        />
        <div className="error">{errorMsg}</div>
      </div>
    );
  }

  return (
    <div className="page-body" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ShelfBreadcrumb
        backTo="/memory"
        backLabel="返回项目记忆库"
        items={[
          { label: "项目记忆库", to: "/memory" },
          { label: overview?.project_name ?? `项目 #${projectId}` },
          { label: "记忆档案馆" },
        ]}
      />
      <div className="subheader">
        <h2 className="serif">❖ {overview?.project_name ?? `项目 #${projectId}`} · 记忆档案馆</h2>
        {overview && (
          <span className="meta">
            健康 {overview.health_score != null ? overview.health_score.toFixed(2) : "—"}
            {" · "}
            7 柜总数 {Object.values(overview.counts).reduce((s, v) => s + v, 0)}
            {" · "}
            裁决 {overview.decision_summary.decided ?? 0} 已 / {overview.decision_summary.pending ?? 0} 待 / {overview.decision_summary.running ?? 0} 跑
          </span>
        )}
      </div>

      {errorMsg && <div className="error" style={{ fontSize: 11 }}>{errorMsg}</div>}

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "260px 1fr 320px", minHeight: 0, gap: 12 }}>
        {/* 左: 8 柜 tabs (7 档案柜 + 1 讨论 + 1 原始) */}
        <CabinetTabs
          counts={overview?.counts ?? {}}
          decisionSummary={overview?.decision_summary ?? {}}
          rawCount={0 /* raw 总数在 overview 没返, entities tab 内部拉 */}
          active={activeCabinet}
          onChange={(k) => { setActiveCabinet(k); setSearch(""); }}
        />

        {/* 中: 当前 cabinet 内容 */}
        <div style={{ overflow: "auto", background: "var(--bg-base)", borderRadius: 4, border: "1px solid var(--accent-line-soft)" }}>
          {activeCabinet === "decisions" ? (
            <DecisionsList
              items={decisions}
              onRun={onRunDecision}
              onApply={onApplyDecision}
            />
          ) : activeCabinet === "raw" ? (
            <RawList items={rawEntries} />
          ) : (
            <>
              <div style={{ padding: 8, borderBottom: "1px solid var(--accent-line-soft)", display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  className="input"
                  placeholder="🔍 搜索名字 / 别名 / tag"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{ maxWidth: 320 }}
                />
                <span className="meta" style={{ fontSize: 11 }}>
                  {filteredEntities.length} 个 {CABINET_CONFIG[activeCabinet as CabinetType].label}
                </span>
              </div>
              {filteredEntities.length === 0 ? (
                <div className="empty-large">
                  <div className="empty-large-glyph">{CABINET_CONFIG[activeCabinet as CabinetType].emoji}</div>
                  <h3>{CABINET_CONFIG[activeCabinet as CabinetType].label}还是空的</h3>
                  <p>这一柜目前没有稳定实体。<br />等 MemoryUpdateAgent 写入原始记忆 → Consolidator 二次加工后会填进来。</p>
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8, padding: 8 }}>
                  {filteredEntities.map((e) => (
                    <EntityCard key={e.id} entity={e} onClick={() => onSelectEntity(e.id)} selected={selectedEntity?.id === e.id} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* 右: 选中实体 / 选中决策 详情 */}
        <div style={{ overflow: "auto", background: "var(--bg-base)", borderRadius: 4, border: "1px solid var(--accent-line-soft)", padding: 12, fontSize: 12 }}>
          {activeCabinet === "decisions" ? (
            <div className="muted">点中间的决策查看裁决详情。</div>
          ) : activeCabinet === "raw" ? (
            <div className="muted">原始记忆是只读的追溯池 (P3 §14 禁 5), 修改在 discussion / consolidate 层做。</div>
          ) : selectedEntity ? (
            <EntityDetail detail={selectedEntity} />
          ) : (
            <div className="muted">点中间一个实体查看详情 (人物档案可看最新状态 + 时间线)。</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ----- 8 柜 tabs (7 档案柜 + 讨论 + 原始) -------------------------
function CabinetTabs({
  counts, decisionSummary, rawCount, active, onChange,
}: {
  counts: Record<string, number>;
  decisionSummary: Record<string, number>;
  rawCount: number;
  active: CabinetType | "decisions" | "raw";
  onChange: (k: CabinetType | "decisions" | "raw") => void;
}) {
  return (
    <div style={{ background: "var(--bg-base)", borderRadius: 4, border: "1px solid var(--accent-line-soft)", padding: 8, overflow: "auto" }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, padding: "0 4px 6px" }}>
        7 档案柜
      </div>
      {CABINETS.map((c) => {
        const n = counts[c.key] ?? 0;
        const isActive = active === c.key;
        return (
          <button
            key={c.key}
            className="cabinet-tab"
            data-active={isActive}
            data-color={CABINET_COLOR[c.key]}
            onClick={() => onChange(c.key)}
            title={c.label}
          >
            <span className="cabinet-tab-emoji">{c.emoji}</span>
            <span className="cabinet-tab-label">{c.label}</span>
            <span className="cabinet-tab-count">{n}</span>
          </button>
        );
      })}
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, padding: "12px 4px 6px" }}>
        冲突 → 讨论
      </div>
      <button
        className="cabinet-tab"
        data-active={active === "decisions"}
        data-color="purple"
        onClick={() => onChange("decisions")}
        title="讨论裁决记录 (P3 §5: 冲突不单独暴露, 走这里)"
      >
        <span className="cabinet-tab-emoji">💬</span>
        <span className="cabinet-tab-label">讨论裁决</span>
        <span className="cabinet-tab-count">{(decisionSummary.decided ?? 0) + (decisionSummary.pending ?? 0) + (decisionSummary.running ?? 0)}</span>
      </button>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, padding: "12px 4px 6px" }}>
        原始记忆池
      </div>
      <button
        className="cabinet-tab"
        data-active={active === "raw"}
        data-color="gray"
        onClick={() => onChange("raw")}
        title="MemoryUpdateAgent 写入的原始记忆池, P3 §14 禁 5: 不删除"
      >
        <span className="cabinet-tab-emoji">📋</span>
        <span className="cabinet-tab-label">原始记忆</span>
        <span className="cabinet-tab-count">{rawCount || "—"}</span>
      </button>
    </div>
  );
}

// ----- 单实体卡片 (7 柜共用) ------------------------------------
function EntityCard({ entity, onClick, selected }: { entity: StableMemoryEntity; onClick: () => void; selected: boolean }) {
  const c = CABINET_CONFIG[entity.entity_type];
  return (
    <button
      onClick={onClick}
      className="entity-card"
      data-color={CABINET_COLOR[entity.entity_type]}
      data-selected={selected ? "1" : "0"}
      title={`${entity.canonical_name} (${c.label})`}
    >
      <div className="entity-card-title">
        <span style={{ marginRight: 4 }}>{c.emoji}</span>
        {entity.canonical_name}
        {entity.aliases.length > 0 && (
          <span className="entity-card-aliases" title={entity.aliases.join(", ")}>
            {" "}· 别名 {entity.aliases.length}
          </span>
        )}
      </div>
      <div className="entity-card-meta">
        {entity.tags.slice(0, 4).map((t) => (
          <span key={t} className="entity-card-tag">{t}</span>
        ))}
        {entity.tags.length > 4 && <span className="entity-card-tag">+{entity.tags.length - 4}</span>}
      </div>
      <div className="entity-card-footer">
        <span className="pill tiny" data-color={CABINET_COLOR[entity.entity_type]}>{c.label}</span>
        <span className="entity-card-conf" title={`置信度 ${(entity.confidence * 100).toFixed(0)}%`}>
          {(entity.confidence * 100).toFixed(0)}%
        </span>
      </div>
    </button>
  );
}

// ----- 单实体详情 (右侧) ----------------------------------------
function EntityDetail({ detail }: { detail: StableMemoryEntityDetail }) {
  const c = CABINET_CONFIG[detail.entity_type];
  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <span className="pill tiny" data-color={CABINET_COLOR[detail.entity_type]}>
          {c.emoji} {c.label}
        </span>
        <b style={{ marginLeft: 6, fontSize: 14 }}>{detail.canonical_name}</b>
      </div>

      {detail.aliases.length > 0 && (
        <Section title="别名">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
            {detail.aliases.map((a) => <span key={a} className="entity-card-tag">{a}</span>)}
          </div>
        </Section>
      )}

      {detail.tags.length > 0 && (
        <Section title="标签">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
            {detail.tags.map((t) => <span key={t} className="entity-card-tag">{t}</span>)}
          </div>
        </Section>
      )}

      {Object.keys(detail.profile).length > 0 && (
        <Section title="Profile">
          <pre style={{ fontSize: 10, background: "var(--bg-elevated)", padding: 6, borderRadius: 3, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap" }}>
            {JSON.stringify(detail.profile, null, 2)}
          </pre>
        </Section>
      )}

      {detail.entity_type === "character" && detail.latest_state && (
        <Section title="最新状态">
          <Field k="所在" v={detail.latest_state.current_location} />
          <Field k="阵营" v={detail.latest_state.current_faction} />
          <Field k="目标" v={detail.latest_state.current_goal} />
          <Field k="情绪" v={detail.latest_state.emotion_state} />
          <Field k="伤势" v={detail.latest_state.injury_state} />
          <Field k="战力" v={detail.latest_state.power_state} />
          {detail.latest_state.owned_items.length > 0 && (
            <Field k="持有物品" v={detail.latest_state.owned_items.join("、")} />
          )}
          {detail.latest_state.abilities.length > 0 && (
            <Field k="能力" v={detail.latest_state.abilities.join("、")} />
          )}
          {detail.latest_state.secrets.length > 0 && (
            <Field k="秘密" v={detail.latest_state.secrets.join("、")} />
          )}
        </Section>
      )}

      <Section title={`时间线 (${detail.timeline.length})`}>
        {detail.timeline.length === 0 ? (
          <div className="muted small">无 timeline 事件</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {detail.timeline.slice(0, 10).map((ev) => (
              <li key={ev.id} style={{ marginBottom: 6, fontSize: 11 }}>
                <b>{ev.event_title}</b>
                {ev.chapter_index != null && <span className="muted"> · 第 {ev.chapter_index} 章</span>}
                {ev.event_summary && <div className="muted" style={{ fontSize: 10 }}>{ev.event_summary.slice(0, 120)}</div>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="muted" style={{ fontSize: 10, marginTop: 8 }}>
        置信度 {(detail.confidence * 100).toFixed(0)}% · 重要度 {(detail.importance * 100).toFixed(0)}% · 状态 {detail.status}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}
function Field({ k, v }: { k: string; v: any }) {
  if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) return null;
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 2, fontSize: 11 }}>
      <span className="muted" style={{ minWidth: 60 }}>{k}</span>
      <span style={{ flex: 1 }}>{String(v)}</span>
    </div>
  );
}

// ----- 讨论裁决记录 ---------------------------------------------
function DecisionsList({
  items, onRun, onApply,
}: {
  items: DiscussionDecision[];
  onRun: (id: number) => void;
  onApply: (id: number) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="empty-large">
        <div className="empty-large-glyph">💬</div>
        <h3>讨论裁决记录是空的</h3>
        <p>Consolidator 跑时遇到不能自动决定的内容 (人物去重 / 字段冲突 / 伏笔不清), 会创建 DiscussionDecision。<br />
        走 DiscussionAgent 拿结果后, apply 写回 Stable。</p>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: 8 }}>
      {items.map((d) => (
        <div key={d.id} className="decision-card" data-status={d.status}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <div>
              <span className="pill tiny">{DECISION_TOPIC_TYPE_LABEL[d.topic_type] ?? d.topic_type}</span>
              <b style={{ marginLeft: 6 }}>{d.topic_title}</b>
            </div>
            <span className="pill tiny" data-color={
              d.status === "decided" ? "green" :
              d.status === "running" ? "purple" :
              d.status === "failed"  ? "red"   : "blue"
            }>
              {DECISION_STATUS_LABEL[d.status] ?? d.status}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>
            #{d.id} · {d.raw_entry_ids.length} 条原始 · {d.related_entity_ids.length} 个实体 ·{" "}
            {new Date(d.created_at).toLocaleString("zh-CN")}
          </div>
          {d.decision && (
            <div style={{ fontSize: 11, padding: 6, background: "var(--bg-elevated)", borderRadius: 3, marginBottom: 4 }}>
              <b>裁决:</b> {d.decision}
              {d.decision_payload && Object.keys(d.decision_payload).length > 0 && (
                <pre style={{ fontSize: 9, margin: "4px 0 0", maxHeight: 80, overflow: "auto" }}>
                  {JSON.stringify(d.decision_payload, null, 2)}
                </pre>
              )}
              {d.reason && <div className="muted" style={{ marginTop: 2, fontSize: 10 }}>{d.reason}</div>}
            </div>
          )}
          <div style={{ display: "flex", gap: 4 }}>
            {d.status === "pending" && (
              <button className="tiny" onClick={() => onRun(d.id)} title="跑 DiscussionAgent 拿裁决 (P3 stub)">
                ▶ 跑裁决
              </button>
            )}
            {d.status === "decided" && (
              <button className="tiny primary" onClick={() => onApply(d.id)} title="把裁决写回 Stable">
                ✓ Apply
              </button>
            )}
            {d.status === "failed" && (
              <button className="tiny" onClick={() => onRun(d.id)} title="重试">
                ↻ 重跑
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ----- 原始记忆池 (只读) ----------------------------------------
function RawList({ items }: { items: RawMemoryEntry[] }) {
  if (items.length === 0) {
    return (
      <div className="empty-large">
        <div className="empty-large-glyph">📋</div>
        <h3>原始记忆池是空的</h3>
        <p>MemoryUpdateAgent 在每个章节跑完后会写入。P3 §14 禁 5: 禁止删除, 这里只读。</p>
      </div>
    );
  }
  return (
    <div style={{ padding: 8 }}>
      <div className="muted small" style={{ marginBottom: 6 }}>
        {items.length} 条原始记忆 (P3 §14 禁 5: 不可删除, 永久保留追溯)
      </div>
      {items.map((r) => (
        <div key={r.id} className="raw-card" data-status={r.status}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
            <b style={{ fontSize: 11 }}>{r.subject}</b>
            <span className="pill tiny" data-color={
              r.status === "merged" || r.status === "decided" ? "green" :
              r.status === "raw" ? "blue" :
              r.status === "needs_discussion" ? "purple" :
              r.status === "rejected" ? "red" : "gray"
            }>
              {r.status}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 10 }}>
            {r.entry_type}
            {r.predicate && ` · ${r.predicate}`}
            {r.object_value && ` · ${r.object_value}`}
            {r.chapter_index != null && ` · 第 ${r.chapter_index} 章`}
            {` · ${r.agent_name}`}
            {` · 置信度 ${(r.confidence * 100).toFixed(0)}%`}
          </div>
          {r.source_quote && (
            <div style={{ fontSize: 10, fontStyle: "italic", color: "var(--text-muted)", marginTop: 2 }}>
              "{r.source_quote.slice(0, 100)}{r.source_quote.length > 100 ? "…" : ""}"
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
