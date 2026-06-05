/**
 * ProjectsPage — 项目书架 (P1)
 *
 * P0 阶段: 卡片列表,所有项目平铺,点击进工作台.
 * P1 阶段 (02_P1_项目书架_项目工作台重构): 改成 ShelfLayout 三栏
 * 书架,按 6 层分组,书脊卡片,右侧详情卡,左侧总览+工具条.
 *
 * 整体结构 (P1 §2.1):
 *
 *   ┌──────────┬─────────────────────┬─────────────┐
 *   │ 工具条   │  项目书架 (6 层横架) │ 选中项目详情 │
 *   │ 搜索     │   ├ 置顶/当前主写    │  + 打开工作台│
 *   │ 状态过滤 │   ├ 玄幻/仙侠/长篇   │  + 置顶/取消 │
 *   │ 类型过滤 │   ├ 都市/科幻/悬疑   │  + 删除      │
 *   │ + 新建   │   ├ 草稿/企划        │             │
 *   │          │   ├ 归档/完结        │             │
 *   │ 总览卡   │   └ 测试/失败项目    │             │
 *   │ 今日任务 │                     │             │
 *   │ Worker   │                     │             │
 *   │ 选中进度 │                     │             │
 *   └──────────┴─────────────────────┴─────────────┘
 *
 * 数据接口 (P1 §8): 不新增 GET /api/projects/shelf 端点,前端基于
 * GET /api/projects 直接分组. 这样:
 *  - 后端零改动, P1 不破坏 R0~R25 任何 API
 *  - 分组规则 (置顶 / 类型 / 归档 / 测试) 在前端一处可见
 *  - 后端要加聚合端点是 P5 (联调验收) 的事
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";
import { useWorkerStore } from "../stores/workerStore";
import { createProject, deleteProject, listTasks, touchProject, updateProject } from "../api";
import type { AgentTask, Project, WorkerStatus } from "../types";
import {
  ShelfLayout, ShelfRow, ShelfBook, ShelfToolbar,
  ShelfSidePanel, ShelfDetailPanel,
  type ShelfColorType,
} from "../components/shelf";

const GENRES = ["玄幻", "都市", "历史", "科幻", "悬疑", "言情", "武侠", "仙侠", "奇幻", "军事", "游戏", "体育"];

// ----- 状态 -> 颜色 + 标签 (P1 §5) -------------------------------------
// spec 写的是规划,目前 backend Project.status 是 String(20) 无 enum 校验,
// 只有默认 "active". 这里宽松映射: 任何未识别值都 fallback 到 blue/进行中.
const STATUS_TO_COLOR: Record<string, ShelfColorType> = {
  active:    "blue",
  running:   "purple",
  completed: "gold",   // spec 写 "绿色或金色" — 完结偏金色
  done:      "gold",
  finished:  "gold",
  draft:     "green",  // spec: 企划 → 绿
  planning:  "green",
  blocked:   "red",
  failed:    "red",
  archived:  "gray",
};
const STATUS_TO_LABEL: Record<string, string> = {
  active:    "进行中",
  running:   "Worker工作中",
  completed: "已完结",
  done:      "已完结",
  finished:  "已完结",
  draft:     "企划中",
  planning:  "企划中",
  blocked:   "卡住",
  failed:    "失败",
  archived:  "已归档",
};
function colorOf(p: Project): ShelfColorType {
  // pinned 项目主写 = blue,优先级最高,显示更突出
  if (p.pinned) return "blue";
  return STATUS_TO_COLOR[p.status] ?? "blue";
}
function labelOf(p: Project): string {
  return STATUS_TO_LABEL[p.status] ?? p.status ?? "进行中";
}

// ----- 分组规则 (P1 §4) -------------------------------------------------
// 顺序就是 spec 给的 6 层顺序. 每层:
type Group = {
  key: string;       // 内部 key
  title: string;     // 横架标题
  hint: string;      // 空架提示
  match: (p: Project) => boolean;
};

// 6 个 genre 大类映射 (P1 §4 跟 spec 完全一致):
const FANTASY_GENRES = new Set(["玄幻", "仙侠", "奇幻", "武侠"]);
const MODERN_GENRES  = new Set(["都市", "科幻", "悬疑"]);
const TEST_HINTS     = ["测试", "test", "试读", "样章", "demo"];

function isTestProject(p: Project): boolean {
  const name = p.name.toLowerCase();
  return TEST_HINTS.some((h) => name.includes(h));
}

const GROUPS: Group[] = [
  {
    key: "pinned",   title: "置顶 / 当前主写",
    hint: "— 没有置顶项目 — 选中项目书脊 → 右侧「置顶」可置顶 —",
    match: (p) => p.pinned,
  },
  {
    key: "fantasy",  title: "玄幻 / 仙侠 / 长篇",
    hint: "— 这一格还没有玄幻 / 仙侠 / 奇幻 / 武侠 项目 —",
    match: (p) => !p.pinned && FANTASY_GENRES.has(p.genre),
  },
  {
    key: "modern",   title: "都市 / 科幻 / 悬疑",
    hint: "— 这一格还没有都市 / 科幻 / 悬疑 项目 —",
    match: (p) => !p.pinned && MODERN_GENRES.has(p.genre),
  },
  {
    key: "draft",    title: "草稿 / 企划",
    hint: "— 这一格还没有草稿 / 企划中项目 (status = draft/planning) —",
    match: (p) => !p.pinned && (p.status === "draft" || p.status === "planning"),
  },
  {
    key: "archived", title: "归档 / 完结",
    hint: "— 这一格还没有归档 / 完结项目 (status = archived/completed) —",
    match: (p) => !p.pinned && (p.status === "archived" || p.status === "completed" || p.status === "done" || p.status === "finished"),
  },
  {
    key: "test",     title: "测试 / 失败项目",
    hint: "— 没有测试项目 / 失败项目 (书名含 测试/test/试读/样章/demo) —",
    match: (p) => !p.pinned && (isTestProject(p) || p.status === "failed" || p.status === "blocked"),
  },
];

// 把 projects 按 6 层分桶,每层保持 backend 排序 (pinned DESC, sort_order ASC)
function bucketProjects(projects: Project[]): Record<string, Project[]> {
  const buckets: Record<string, Project[]> = {};
  for (const g of GROUPS) buckets[g.key] = [];
  for (const p of projects) {
    for (const g of GROUPS) {
      if (g.match(p)) { buckets[g.key].push(p); break; }
    }
  }
  return buckets;
}

// hover 提示信息 (P1 §3)
function buildHoverText(p: Project, recentTask: AgentTask | null, avgScore: number | null, worker: WorkerStatus | null): string {
  const pct = p.target_word_count > 0
    ? Math.round((p.total_words / p.target_word_count) * 100)
    : 0;
  const lines = [
    `书名: ${p.name}`,
    `类型: ${p.genre}${p.category ? ` (${p.category})` : ""} · 状态: ${labelOf(p)}`,
    `已写章节: ${p.chapter_count} / 目标 ${p.target_chapter_count}`,
    `已写字数: ${formatNumber(p.total_words)} / 目标 ${formatNumber(p.target_word_count)} (${pct}%)`,
  ];
  if (avgScore != null) lines.push(`平均分: ${avgScore}`);
  if (recentTask) {
    lines.push(`最近任务: #${recentTask.id} ${recentTask.task_type} · ${recentTask.status} · $${recentTask.cost_usd.toFixed(4)}`);
  } else {
    lines.push(`最近任务: 无`);
  }
  if (worker) {
    lines.push(`Worker: ${worker.state}${worker.is_loop_alive ? " · 循环存活" : ""}${worker.current_task_id ? ` · 任务 #${worker.current_task_id}` : ""}`);
  }
  return lines.join("\n");
}

// 数字格式: 万 / 亿
function formatNumber(n: number): string {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(2)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`;
  return n.toLocaleString();
}

// ----- 主组件 -----------------------------------------------------------
export function ProjectsPage() {
  const projects = useProjectStore((s) => s.projects);
  const refresh = useProjectStore((s) => s.refresh);
  const removeFromStore = useProjectStore((s) => s.removeProject);
  const select = useProjectStore((s) => s.selectProject);
  const worker = useWorkerStore((s) => s.status);
  const refreshWorker = useWorkerStore((s) => s.refresh);
  const navigate = useNavigate();

  // 选中项目
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // 搜索 / 过滤
  const [search, setSearch] = useState("");
  const [genreFilter, setGenreFilter] = useState<string | "all">("all");
  // 今日任务 + 今日成本 (给左侧总览用)
  const [todayTasks, setTodayTasks] = useState<AgentTask[]>([]);
  // 新建项目 modal
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("玄幻");
  const [targetWords, setTargetWords] = useState(3_000_000);
  const [targetChapters, setTargetChapters] = useState(2000);
  const [description, setDescription] = useState("");
  const [pinnedOnCreate, setPinnedOnCreate] = useState(false);
  const [busy, setBusy] = useState(false);

  // mount: 拉项目 + worker 状态
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { refreshWorker(); }, [refreshWorker]);
  // 今日任务: 每 5s 拉一次(轻量,不阻塞)
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      listTasks({ limit: 100 }).then((rows) => {
        if (cancelled) return;
        // 过滤"今日" — 后端 created_at 是 ISO 字符串,前端按本地零点算
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const todayMs = today.getTime();
        const todays = rows.filter((t) => {
          const c = new Date(t.created_at).getTime();
          return c >= todayMs;
        });
        setTodayTasks(todays);
      }).catch(() => {});
    };
    load();
    const h = window.setInterval(load, 5000);
    return () => { cancelled = true; window.clearInterval(h); };
  }, []);

  // 过滤后项目
  const filteredProjects = useMemo(() => {
    let rows = projects;
    if (genreFilter !== "all") rows = rows.filter((p) => p.genre === genreFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((p) =>
        p.name.toLowerCase().includes(q)
        || (p.description ?? "").toLowerCase().includes(q)
        || (p.category ?? "").toLowerCase().includes(q),
      );
    }
    return rows;
  }, [projects, search, genreFilter]);

  // 分桶
  const buckets = useMemo(() => bucketProjects(filteredProjects), [filteredProjects]);

  // 默认选中第一个项目 (mount 后,如果有项目)
  useEffect(() => {
    if (selectedId == null && projects.length > 0) setSelectedId(projects[0].id);
  }, [selectedId, projects]);

  const selected = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );

  // 选中项目最近任务
  const selectedRecentTask = useMemo(() => {
    if (!selected) return null;
    return todayTasks.find((t) => t.project_id === selected.id) ?? null;
  }, [todayTasks, selected]);

  // 选中项目平均分: 后端 ProjectRead 没有 avg_score 字段,只能从 tasks / chapters 估算
  // 这里给 0 让用户能看到进度,但不显示虚高假数据
  const selectedAvgScore: number | null = null;

  // 总览统计 (左侧)
  const totalCount = projects.length;
  const activeCount = projects.filter((p) => p.status === "active" || p.status === "running").length;
  const pinnedCount = projects.filter((p) => p.pinned).length;
  const archivedCount = projects.filter((p) => p.status === "archived" || p.status === "completed" || p.status === "done").length;
  const todayCost = todayTasks.reduce((s, t) => s + (t.cost_usd ?? 0), 0);
  const todaySucceeded = todayTasks.filter((t) => t.status === "succeeded").length;
  const todayFailed = todayTasks.filter((t) => t.status === "failed").length;

  // 操作 ----------------------------------------------------------------
  const openProject = async (p: Project) => {
    select(p.id);
    setSelectedId(p.id);
    // 触一下 last_opened_at (P0-UI-2 / Round 2 留下来的接口)
    try { await touchProject(p.id); } catch { /* 不阻塞跳转 */ }
    navigate(`/projects/${p.id}`);
  };

  const onCreate = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const p = await createProject({
        name: name.trim(), genre,
        target_word_count: targetWords, target_chapter_count: targetChapters,
        description: description.trim() || null,
        pinned: pinnedOnCreate,
      });
      setCreating(false);
      setName(""); setDescription(""); setPinnedOnCreate(false);
      await refresh();
      setSelectedId(p.id);
      select(p.id);
    } catch (e: any) {
      alert(e.message ?? String(e));
    } finally { setBusy(false); }
  };

  const onDelete = async (p: Project) => {
    // P1 §10 验收 7: 删除仍需要二次确认 (P1 §11 禁 4: 不破坏创建功能 — 同理不破坏删除)
    if (!confirm(`确认删除「${p.name}」？\n所有章节 / 大纲 / 任务 / 设定 / 记忆都会被清除,无法恢复。`)) return;
    try {
      await deleteProject(p.id);
      removeFromStore(p.id);
      if (selectedId === p.id) setSelectedId(null);
    } catch (e: any) { alert(e.message ?? String(e)); }
  };

  const togglePin = async (p: Project) => {
    try {
      const updated = await updateProject(p.id, { pinned: !p.pinned });
      useProjectStore.setState((s) => {
        const idx = s.projects.findIndex((x) => x.id === updated.id);
        if (idx < 0) return s;
        const list = s.projects.slice();
        list[idx] = updated;
        return { projects: list };
      });
    } catch (e: any) { alert(e.message ?? String(e)); }
  };

  // 渲染 ----------------------------------------------------------------
  return (
    <ShelfLayout
      left={
        <>
          <ShelfToolbar>
            <input
              className="input"
              placeholder="🔍 搜索项目 (书名 / 简介 / 分类)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="shelf-toolbar-chips">
              <button
                className={`shelf-toolbar-chip ${genreFilter === "all" ? "active" : ""}`}
                onClick={() => setGenreFilter("all")}
              >
                全部 ({totalCount})
              </button>
              {GENRES.map((g) => {
                const n = projects.filter((p) => p.genre === g).length;
                if (n === 0) return null;
                return (
                  <button
                    key={g}
                    className={`shelf-toolbar-chip ${genreFilter === g ? "active" : ""}`}
                    onClick={() => setGenreFilter(g)}
                  >
                    {g} ({n})
                  </button>
                );
              })}
            </div>
            <button className="primary" onClick={() => setCreating(true)}>
              + 新建项目
            </button>
          </ShelfToolbar>

          <ShelfSidePanel
            title="项目总览"
            accentColor="blue"
          >
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <Stat label="总项目" value={totalCount} />
              <Stat label="进行中" value={activeCount} />
              <Stat label="置顶" value={pinnedCount} />
              <Stat label="归档" value={archivedCount} />
            </div>
          </ShelfSidePanel>

          <ShelfSidePanel
            title="今日 Worker"
            accentColor={worker?.is_loop_alive ? "green" : "gray"}
          >
            {worker ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
                <Stat label="状态" value={worker.state} />
                <Stat label="今日任务" value={todayTasks.length} />
                <Stat label="今日成本" value={`$${todayCost.toFixed(4)}`} />
                <Stat label="成功/失败" value={`${todaySucceeded}/${todayFailed}`} />
                {worker.current_task_id != null && (
                  <div style={{ gridColumn: "1 / -1", fontSize: 11, color: "var(--text-muted)" }}>
                    当前任务: #{worker.current_task_id}
                  </div>
                )}
                {!worker.is_loop_alive && (
                  <div style={{ gridColumn: "1 / -1", color: "var(--accent-red, #c45858)", fontSize: 11 }}>
                    ⚠ 循环未存活 — Worker 不在轮询
                  </div>
                )}
              </div>
            ) : (
              <div className="muted small">加载中…</div>
            )}
          </ShelfSidePanel>

          <ShelfSidePanel
            title="选中项目进度"
            accentColor={selected ? colorOf(selected) : "gray"}
          >
            {selected ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
                <Stat label="已写章节" value={`${selected.chapter_count} / ${selected.target_chapter_count}`} />
                <Stat label="已写字数" value={formatNumber(selected.total_words)} />
                <Stat
                  label="字数进度"
                  value={`${Math.round((selected.total_words / selected.target_word_count) * 100)}%`}
                />
                <Stat label="状态" value={labelOf(selected)} />
                {selectedRecentTask && (
                  <div style={{ gridColumn: "1 / -1", fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                    最近任务: #{selectedRecentTask.id} {selectedRecentTask.task_type} · {selectedRecentTask.status}
                  </div>
                )}
              </div>
            ) : (
              <div className="muted small">在中间书架点一本项目册 → 这里显示该书的进度</div>
            )}
          </ShelfSidePanel>
        </>
      }
      center={
        <>
          {projects.length === 0 ? (
            <div className="empty-large">
              <div className="empty-large-glyph">书</div>
              <h3>书架还是空的</h3>
              <p>点左上方「+ 新建项目」开始你的第一本书。</p>
            </div>
          ) : (
            GROUPS.map((g) => (
              <ShelfRow
                key={g.key}
                title={g.title}
                subtitle={`(${buckets[g.key].length} 本)`}
                emptyHint={g.hint}
              >
                {buckets[g.key].map((p) => {
                  const pct = p.target_word_count > 0
                    ? Math.min(100, Math.round((p.total_words / p.target_word_count) * 100))
                    : 0;
                  // P1 §3: 悬停显示完整信息 (章节/字数/任务/Worker)
                  // 走 ShelfBook 的 hoverHint (HTML 原生 title) 注入
                  return (
                    <ShelfBook
                      key={p.id}
                      title={p.name}
                      subtitle={`${p.genre} · ${labelOf(p)}`}
                      status={p.pinned ? "★ 置顶" : labelOf(p)}
                      progressPct={pct}
                      progressLabel={`${formatNumber(p.total_words)} / ${formatNumber(p.target_word_count)} 字`}
                      colorType={colorOf(p)}
                      selected={selectedId === p.id}
                      onClick={() => { setSelectedId(p.id); select(p.id); }}
                      hoverHint={buildHoverText(
                        p,
                        todayTasks.find((t) => t.project_id === p.id) ?? null,
                        null,
                        worker,
                      )}
                    />
                  );
                })}
              </ShelfRow>
            ))
          )}
        </>
      }
      right={
        <ShelfDetailPanel
          title={selected?.name ?? "未选中项目"}
          subtitle={selected ? `${selected.genre} · ${labelOf(selected)} · #${selected.id}` : "点中间书架里的一本项目册查看详情"}
          accentColor={selected ? colorOf(selected) : "gray"}
          stats={selected ? [
            { label: "已写章节", value: `${selected.chapter_count} / ${selected.target_chapter_count}` },
            { label: "已写字数", value: formatNumber(selected.total_words) },
            { label: "字数进度", value: `${Math.round((selected.total_words / selected.target_word_count) * 100)}%` },
            { label: "状态", value: labelOf(selected) },
            { label: "创建", value: new Date(selected.created_at).toLocaleDateString("zh-CN") },
            { label: "最近打开", value: selected.last_opened_at ? new Date(selected.last_opened_at).toLocaleString("zh-CN") : "—" },
            { label: "目标字数", value: formatNumber(selected.target_word_count) },
            { label: "目标章节", value: selected.target_chapter_count.toLocaleString() },
          ] : []}
          actions={selected ? (
            <>
              <button
                className="primary"
                onClick={() => openProject(selected)}
                title="进入项目工作台"
              >
                📖 打开项目工作台
              </button>
              <button onClick={() => togglePin(selected)}>
                {selected.pinned ? "★ 取消置顶" : "☆ 置顶"}
              </button>
              <button
                onClick={() => navigate(`/memory/${selected.id}`)}
                title="查看该项目记忆册"
              >
                📚 项目记忆
              </button>
              <button
                onClick={() => onDelete(selected)}
                style={{ color: "var(--accent-red, #c45858)" }}
              >
                删除项目
              </button>
            </>
          ) : null}
        >
          {selected ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
              {selected.description && (
                <div style={{ lineHeight: 1.6, color: "var(--text-secondary)" }}>
                  {selected.description}
                </div>
              )}
              <div style={{
                padding: 8,
                background: "var(--bg-elevated)",
                borderRadius: 4,
                fontSize: 11,
                color: "var(--text-muted)",
              }}>
                <div>分类: {selected.category ?? "—"}</div>
                <div>排序: {selected.sort_order}</div>
                <div>Worker 任务 # {selected.id}: {todayTasks.filter((t) => t.project_id === selected.id).length} 条今日</div>
                {selectedRecentTask && (
                  <div>最近: {selectedRecentTask.task_type} · {selectedRecentTask.status} · ${selectedRecentTask.cost_usd.toFixed(4)}</div>
                )}
              </div>
            </div>
          ) : (
            <div className="muted small">点中间书架里的一本项目册,这里会显示该项目的元数据 + 操作按钮。</div>
          )}
        </ShelfDetailPanel>
      }
    />
  );
}

// 左侧小数字
function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
    </div>
  );
}
