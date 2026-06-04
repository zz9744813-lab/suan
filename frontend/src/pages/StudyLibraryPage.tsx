/**
 * StudyLibraryPage — 拆书书架 (P2)
 *
 * P0 阶段: stub, 直接渲染旧 StudyPage (树状 tab + 行为模式).
 * P2 阶段 (03_P2_拆书书架_DeepStudy知识网络): 改成 ShelfLayout 三栏
 * 书架, 跟 P1 项目书架视觉一致, 但书的"密度"更高 (一本大厚书 vs
 * 一个项目).
 *
 * 整体结构 (P2 §2):
 *
 *   ┌──────────┬─────────────────────┬─────────────┐
 *   │ 工具条   │  拆书书架 (分层)     │ 选中书详情  │
 *   │ 搜索     │   ├ 已完成 (3)      │  6 深层     │
 *   │ 状态过滤 │   ├ 拆解中 (2)      │   counter   │
 *   │ + 上传   │   ├ 待分章 (4)      │  启动按钮  │
 *   │ + 粘贴   │   ├ 失败/待修 (1)   │  打开网络  │
 *   │          │   └ 草稿 (2)        │  行为 / 技巧│
 *   │ 8 状态卡 │                     │             │
 *   │ 全局成本 │                     │             │
 *   └──────────┴─────────────────────┴─────────────┘
 *
 * 数据接口 (P2 §7): GET /api/deepstudy/library — R25 (commit efeb960)
 * 加的聚合端点, 一次性返回 items + summary, 6 个深层 counter 各跑一个
 * GROUP BY 计数, 不需要前端 6 次往返.
 *
 * 启动 DeepStudy: ShelfDetailPanel "🚀 启动 DeepStudy" 按钮 →
 * POST /api/deepstudy/materials/{id}/runs { mode: "full" }.
 * 之后轮询 GET /api/deepstudy/runs/{run_id} 2.5s 一次看进度.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  listDeepStudyLibrary,
  startDeepStudyRun,
  getDeepStudyRun,
  pauseDeepStudyRun,
  resumeDeepStudyRun,
  cancelDeepStudyRun,
  listDeepStudyPatterns,
  listDeepStudyTechniques,
} from "../api";
import type {
  LibraryItem,
  LibraryResponse,
  StudyRunRead,
} from "../types";
import {
  ShelfLayout, ShelfRow, ShelfBook, ShelfToolbar,
  ShelfSidePanel, ShelfDetailPanel,
  type ShelfColorType,
} from "../components/shelf";

// ----- 状态 -> 颜色 + 标签 (P2 §2) -------------------------------------
// spec 给的 6 个颜色. 我们的 Shelf 颜色 token 表里没 orange, 走 fallback red
// 并在 hoverHint 里说明, 后续 P2.1 (UI 美化) 加 orange token.
const STATUS_TO_COLOR: Record<string, ShelfColorType> = {
  completed:       "gold",     // 已完成: 高完成度金色 (P0 §5 + P2 §2 一致)
  studying:        "purple",   // 拆解中: 紫色发光
  chapterized:     "green",    // 已分章: 绿色
  failed:          "red",      // 失败: 红
  review_required: "red",      // 待修: 红 (P2 §2 写 orange, 当前 token 表里没, 走红)
  uploaded:        "gray",     // 已上传未分章
  empty:           "gray",     // 空 (未上传)
  paused:          "blue",     // 暂停: 主写蓝 (spec 没说, 跟"用户主动停止"对应)
};
const STATUS_TO_LABEL: Record<string, string> = {
  empty:           "空",
  uploaded:        "已上传",
  chapterized:     "已分章",
  studying:        "拆解中",
  paused:          "已暂停",
  review_required: "待复审",
  completed:       "已完成",
  failed:          "失败",
};
function colorOf(it: LibraryItem): ShelfColorType {
  return STATUS_TO_COLOR[it.study_status] ?? "gray";
}
function labelOf(it: LibraryItem): string {
  return STATUS_TO_LABEL[it.study_status] ?? it.study_status;
}

// ----- 分组规则 (P2 §2) -----------------------------------------------
// 书架上 5 个分层 (按进度从"老"到"新"排):
//   1. 已完成        study_status = completed
//   2. 拆解中        study_status = studying
//   3. 待分章        study_status = uploaded | empty
//   4. 失败/待修     study_status = failed | review_required
//   5. 已暂停        study_status = paused
//   6. 草稿          shelf_category = "草稿" (用户手动分桶, 没有就跳过)
type Group = {
  key: string;
  title: string;
  hint: string;
  match: (it: LibraryItem) => boolean;
};
const GROUPS: Group[] = [
  {
    key: "completed", title: "已完成 DeepStudy",
    hint: "— 还没有书跑完 DeepStudy (study_status=completed) —",
    match: (it) => it.study_status === "completed",
  },
  {
    key: "studying",  title: "拆解中",
    hint: "— 没有书正在拆 (study_status=studying) —",
    match: (it) => it.study_status === "studying",
  },
  {
    key: "pending",   title: "待分章 / 待启动",
    hint: "— 这一格还没有「已上传未分章」的书 —",
    match: (it) => it.study_status === "uploaded" || it.study_status === "empty",
  },
  {
    key: "trouble",   title: "失败 / 待复审",
    hint: "— 这一格没有失败 / 待复审的书 —",
    match: (it) => it.study_status === "failed" || it.study_status === "review_required",
  },
  {
    key: "paused",    title: "已暂停",
    hint: "— 没有暂停的拆书 —",
    match: (it) => it.study_status === "paused",
  },
  {
    key: "drafts",    title: "草稿 / 测试书",
    hint: "— shelf_category 含「草稿」的书会落在这里 —",
    match: (it) => (it.shelf_category ?? "").includes("草稿") || (it.shelf_category ?? "").toLowerCase().includes("test"),
  },
];

function bucketItems(items: LibraryItem[]): Record<string, LibraryItem[]> {
  const buckets: Record<string, LibraryItem[]> = {};
  for (const g of GROUPS) buckets[g.key] = [];
  for (const it of items) {
    for (const g of GROUPS) {
      if (g.match(it)) { buckets[g.key].push(it); break; }
    }
  }
  return buckets;
}

// hover 提示 (P2 §2: 书脊应显示章节数 / 已处理 / 知识节点 / 关系 / 行为 / 技巧 / 知识密度)
function buildHover(it: LibraryItem): string {
  const processedPct = it.chapter_count > 0
    ? Math.round((it.processed_chapters / it.chapter_count) * 100)
    : 0;
  return [
    `书名: ${it.title}`,
    `作者: ${it.author || "—"} · 状态: ${labelOf(it)}`,
    `章节: ${it.processed_chapters} / ${it.chapter_count} (${processedPct}%)`,
    `实体: ${it.entity_count} · 场景节拍: ${it.scene_beat_count}`,
    `关系: ${it.relationship_count} · 伏笔: ${it.foreshadow_count}`,
    `行为: ${it.behavior_count} · 技巧: ${it.technique_count}`,
    it.knowledge_score != null ? `知识密度: ${it.knowledge_score.toFixed(2)}` : `知识密度: — (未跑过 StudyCritic)`,
    it.cost_usd > 0 ? `已花成本: $${it.cost_usd.toFixed(4)}` : `已花成本: $0`,
  ].join("\n");
}

// ----- 主组件 -----------------------------------------------------------
export function StudyLibraryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<LibraryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | "all">("all");
  // 当前在跑的 run (id -> Read), ShelfDetailPanel 启动后轮询用
  const [activeRuns, setActiveRuns] = useState<Record<number, StudyRunRead>>({});

  // mount: 拉书架
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      setLoading(true);
      listDeepStudyLibrary({ page: 1, page_size: 200 })
        .then((r) => {
          if (cancelled) return;
          setData(r);
          setErrorMsg(null);
          // 默认选第一本
          if (selectedId == null && r.items.length > 0) setSelectedId(r.items[0].id);
        })
        .catch((e) => {
          if (cancelled) return;
          setErrorMsg(String(e?.message ?? e));
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    load();
    const h = window.setInterval(load, 8000); // 8s 轻量轮询, 书架状态变化慢
    return () => { cancelled = true; window.clearInterval(h); };
  }, [selectedId]);

  // 轮询 active run
  useEffect(() => {
    const ids = Object.keys(activeRuns).map(Number).filter(
      (id) => {
        const s = activeRuns[id]?.status;
        return s === "queued" || s === "running" || s === "paused";
      },
    );
    if (ids.length === 0) return;
    const h = window.setInterval(() => {
      for (const id of ids) {
        getDeepStudyRun(id)
          .then((r) => setActiveRuns((prev) => ({ ...prev, [id]: r })))
          .catch(() => {});
      }
    }, 2500);
    return () => window.clearInterval(h);
  }, [activeRuns]);

  // 过滤后
  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data.items;
    if (statusFilter !== "all") rows = rows.filter((it) => it.study_status === statusFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter((it) =>
        it.title.toLowerCase().includes(q)
        || (it.author ?? "").toLowerCase().includes(q)
        || (it.shelf_category ?? "").toLowerCase().includes(q),
      );
    }
    return rows;
  }, [data, search, statusFilter]);

  const buckets = useMemo(() => bucketItems(filtered), [filtered]);
  const selected = useMemo(
    () => data?.items.find((it) => it.id === selectedId) ?? null,
    [data, selectedId],
  );

  // 操作 ----------------------------------------------------------------
  const startRun = async (it: LibraryItem, mode: StudyRunRead["mode"] = "full") => {
    try {
      const start = await startDeepStudyRun(it.id, { mode, max_concurrency: 3 });
      const initial: StudyRunRead = {
        id: start.run_id,
        material_id: start.material_id,
        project_id: it.project_id,
        status: start.status,
        mode,
        total_chapters: it.chapter_count,
        processed_chapters: 0,
        current_stage: null,
        agent_plan: null,
        progress: null,
        cost_usd: 0,
        input_tokens: 0,
        output_tokens: 0,
        error: null,
        started_at: null,
        finished_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setActiveRuns((prev) => ({ ...prev, [start.run_id]: initial }));
      setErrorMsg(`已启动 run #${start.run_id} (${mode}) — 后台拆解中, 2.5s 自动轮询进度。`);
    } catch (e: any) {
      setErrorMsg(`启动失败: ${e?.message ?? e}`);
    }
  };

  const pauseRun = async (runId: number) => {
    try { await pauseDeepStudyRun(runId); }
    catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };
  const resumeRun = async (runId: number) => {
    try { await resumeDeepStudyRun(runId); }
    catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };
  const cancelRun = async (runId: number) => {
    try { await cancelDeepStudyRun(runId); }
    catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };

  // 当前选中书的 run (按时间倒序 latest)
  const selectedRun = useMemo(() => {
    if (!selected) return null;
    const runs = Object.values(activeRuns).filter((r) => r.material_id === selected.id);
    if (runs.length === 0) return null;
    return runs.sort((a, b) => b.id - a.id)[0];
  }, [activeRuns, selected]);

  // 渲染 ----------------------------------------------------------------
  return (
    <ShelfLayout
      title="拆书书架"
      subtitle="参考书 → 单书知识网络 → 7 类 Agent 深拆, 沉淀行为模式 + 写作技巧。"
      breadcrumb={[{ label: "拆书书架" }]}
      left={
        <>
          <ShelfToolbar>
            <input
              className="input"
              placeholder="🔍 搜索书名 / 作者 / 分桶"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="shelf-toolbar-chips">
              <button
                className={`shelf-toolbar-chip ${statusFilter === "all" ? "active" : ""}`}
                onClick={() => setStatusFilter("all")}
              >
                全部 ({data?.items.length ?? 0})
              </button>
              {Object.entries(STATUS_TO_LABEL).map(([k, label]) => {
                const n = data?.items.filter((it) => it.study_status === k).length ?? 0;
                if (n === 0) return null;
                return (
                  <button
                    key={k}
                    className={`shelf-toolbar-chip ${statusFilter === k ? "active" : ""}`}
                    onClick={() => setStatusFilter(k)}
                  >
                    {label} ({n})
                  </button>
                );
              })}
            </div>
            <button
              className="primary"
              onClick={() => navigate("/study")}
              title="打开旧版 StudyPage (上传 / 粘贴 / 抽人物 / 行为模式 tab)"
            >
              📤 上传 / 粘贴 / 行为模式
            </button>
          </ShelfToolbar>

          {errorMsg && (
            <ShelfSidePanel title="提示" accentColor="red">
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{errorMsg}</div>
            </ShelfSidePanel>
          )}

          {data?.summary && (
            <ShelfSidePanel title="全局统计" accentColor="purple">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
                <Stat label="总书数" value={data.summary.total_books} />
                <Stat label="已完成" value={data.summary.completed} />
                <Stat label="拆解中" value={data.summary.studying} />
                <Stat label="已暂停" value={data.summary.paused} />
                <Stat label="待复审" value={data.summary.review_required} />
                <Stat label="失败" value={data.summary.failed} />
                <Stat label="已分章" value={data.summary.chapterized} />
                <Stat label="未传" value={data.summary.empty} />
              </div>
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--accent-line-soft)", fontSize: 11, color: "var(--text-muted)" }}>
                实体 {data.summary.total_entities} · 关系 {data.summary.total_relationships} · 技巧 {data.summary.total_techniques}
                <br />
                已花 ${data.summary.total_cost_usd.toFixed(4)}
              </div>
            </ShelfSidePanel>
          )}

          {selected && (
            <ShelfSidePanel
              title="选中书进度"
              accentColor={colorOf(selected)}
            >
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
                <Stat label="章节" value={`${selected.processed_chapters} / ${selected.chapter_count}`} />
                <Stat label="实体" value={selected.entity_count} />
                <Stat label="场景" value={selected.scene_beat_count} />
                <Stat label="关系" value={selected.relationship_count} />
                <Stat label="伏笔" value={selected.foreshadow_count} />
                <Stat label="行为" value={selected.behavior_count} />
                <Stat label="技巧" value={selected.technique_count} />
                <Stat
                  label="知识密度"
                  value={selected.knowledge_score != null ? selected.knowledge_score.toFixed(2) : "—"}
                />
              </div>
            </ShelfSidePanel>
          )}
        </>
      }
      center={
        <>
          {loading && !data ? (
            <div className="muted small" style={{ padding: 24 }}>加载书架…</div>
          ) : (data?.items.length ?? 0) === 0 ? (
            <div className="empty-large">
              <div className="empty-large-glyph">📚</div>
              <h3>书架还是空的</h3>
              <p>点左上方「📤 上传 / 粘贴」打开旧版 StudyPage, 先传一本书 / 粘一段正文, 然后回到这里启动 DeepStudy。</p>
            </div>
          ) : (
            GROUPS.map((g) => (
              <ShelfRow
                key={g.key}
                title={g.title}
                subtitle={`(${buckets[g.key].length} 本)`}
                emptyHint={g.hint}
              >
                {buckets[g.key].map((it) => {
                  const processedPct = it.chapter_count > 0
                    ? Math.min(100, Math.round((it.processed_chapters / it.chapter_count) * 100))
                    : 0;
                  return (
                    <ShelfBook
                      key={it.id}
                      title={it.title}
                      subtitle={`${it.author || "—"} · ${it.shelf_category ?? "未分桶"}`}
                      status={labelOf(it)}
                      progressPct={processedPct}
                      progressLabel={`${it.processed_chapters}/${it.chapter_count} 章 · 实体 ${it.entity_count}`}
                      colorType={colorOf(it)}
                      selected={selectedId === it.id}
                      onClick={() => setSelectedId(it.id)}
                      hoverHint={buildHover(it)}
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
          title={selected?.title ?? "未选中参考书"}
          subtitle={selected
            ? `${selected.author || "—"} · ${labelOf(selected)} · #${selected.id}${selected.shelf_category ? ` · ${selected.shelf_category}` : ""}`
            : "点中间书架里的一本参考书查看详情 / 启动 DeepStudy"}
          accentColor={selected ? colorOf(selected) : "gray"}
          stats={selected ? [
            { label: "章节", value: `${selected.processed_chapters} / ${selected.chapter_count}` },
            { label: "实体", value: selected.entity_count },
            { label: "场景节拍", value: selected.scene_beat_count },
            { label: "关系", value: selected.relationship_count },
            { label: "伏笔", value: selected.foreshadow_count },
            { label: "行为模式", value: selected.behavior_count },
            { label: "写作技巧", value: selected.technique_count },
            { label: "知识密度", value: selected.knowledge_score != null ? selected.knowledge_score.toFixed(2) : "—" },
          ] : []}
          actions={selected ? (
            <>
              <button
                className="primary"
                onClick={() => navigate(`/study/books/${selected.id}/graph`)}
                title="进入单书知识网络"
              >
                🌐 打开知识网络
              </button>
              <button onClick={() => navigate("/study")} title="旧版 StudyPage (上传 / 分章 / 抽人物 / 行为模式 tab)">
                📚 旧版详情页
              </button>
              {selectedRun && selectedRun.status === "running" && (
                <button onClick={() => pauseRun(selectedRun.id)}>⏸ 暂停</button>
              )}
              {selectedRun && selectedRun.status === "paused" && (
                <button onClick={() => resumeRun(selectedRun.id)}>▶ 继续</button>
              )}
              {selectedRun && (selectedRun.status === "running" || selectedRun.status === "paused") && (
                <button onClick={() => cancelRun(selectedRun.id)} style={{ color: "var(--accent-red, #c45858)" }}>
                  ✕ 取消
                </button>
              )}
            </>
          ) : null}
        >
          {selected ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12 }}>
              {/* 启动 DeepStudy 区域 */}
              <div style={{
                padding: 10,
                background: "var(--bg-elevated)",
                borderRadius: 4,
                border: "1px solid var(--accent-line-soft)",
              }}>
                <div style={{ marginBottom: 8, color: "var(--text-muted)", fontSize: 11 }}>
                  启动 DeepStudy (P0 多 Agent 流水线):
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  <button
                    className="primary tiny"
                    onClick={() => startRun(selected, "full")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="ChapterProfiler + Entity + SceneBeat + Relationship + Foreshadow + Behavior + Technique + Critic 全跑一遍"
                  >
                    🚀 启动 full
                  </button>
                  <button
                    className="tiny"
                    onClick={() => startRun(selected, "entities_only")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="只跑 ChapterProfiler + Entity + SceneBeat"
                  >
                    👤 仅实体
                  </button>
                  <button
                    className="tiny"
                    onClick={() => startRun(selected, "relationships_only")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="只跑 ChapterProfiler + Relationship"
                  >
                    🔗 仅关系
                  </button>
                  <button
                    className="tiny"
                    onClick={() => startRun(selected, "behaviors_only")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="只跑 ChapterProfiler + Behavior"
                  >
                    🧩 仅行为
                  </button>
                  <button
                    className="tiny"
                    onClick={() => startRun(selected, "techniques_only")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="只跑 Behavior + Technique"
                  >
                    ✍️ 仅技巧
                  </button>
                  <button
                    className="tiny"
                    onClick={() => startRun(selected, "repair_failed")}
                    disabled={!!selectedRun && (selectedRun.status === "running" || selectedRun.status === "queued")}
                    title="重跑上一次 run 失败的 stage (其它不动)"
                  >
                    🔧 修复失败
                  </button>
                </div>
              </div>

              {selectedRun && (
                <RunProgressCard run={selectedRun} />
              )}

              <div style={{
                padding: 8,
                background: "var(--bg-elevated)",
                borderRadius: 4,
                fontSize: 11,
                color: "var(--text-muted)",
              }}>
                <div>DeepStudy 版本: {selected.deepstudy_version ?? "—"}</div>
                <div>已花成本: ${selected.cost_usd.toFixed(4)}</div>
                <div>最后深拆: {selected.last_deepstudied_at ? new Date(selected.last_deepstudied_at).toLocaleString("zh-CN") : "—"}</div>
                <div>创建: {new Date(selected.created_at).toLocaleDateString("zh-CN")}</div>
              </div>
            </div>
          ) : (
            <div className="muted small">点中间书架里的一本参考书, 这里会显示该书的 6 深层 counter + DeepStudy 启动按钮。</div>
          )}
        </ShelfDetailPanel>
      }
    />
  );
}

function Stat({ label, value }: { label: string; value: any }) {
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

function RunProgressCard({ run }: { run: StudyRunRead }) {
  const pct = run.total_chapters > 0
    ? Math.min(100, Math.round((run.processed_chapters / run.total_chapters) * 100))
    : 0;
  const stage = (run.progress as any)?.current_stage ?? run.current_stage ?? "—";
  return (
    <div style={{
      padding: 10,
      background: run.status === "failed" ? "rgba(196,88,88,0.08)" : "var(--bg-elevated)",
      borderRadius: 4,
      border: "1px solid var(--accent-line-soft)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11 }}>
        <b>Run #{run.id} · {run.mode}</b>
        <span className={`pill tiny ${run.status === "failed" ? "error" : run.status === "succeeded" ? "ok" : "warn"}`}>
          {run.status}
        </span>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
        stage: {stage} · {run.processed_chapters} / {run.total_chapters} 章
      </div>
      <div style={{ height: 4, background: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${pct}%`,
          background: run.status === "failed" ? "var(--accent-red, #c45858)" : "var(--accent-gold)",
          transition: "width 0.4s",
        }} />
      </div>
      <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-muted)" }}>
        ${run.cost_usd.toFixed(4)} · {run.input_tokens}→{run.output_tokens} tok
        {run.error && <div style={{ color: "var(--accent-red, #c45858)", marginTop: 2 }}>{run.error}</div>}
      </div>
    </div>
  );
}

/**
 * StudyBookGraphPage — 单书知识网络 (P2)
 *
 * P0 stub 跳到旧 /graph; P2 改成单书知识网络视图, 中心是当前书
 * (符合 P2 §11 禁 3: "禁止图谱一打开就是全局乱图").
 *
 * 复用 R24 的 GraphPage 物理 (D3 渲染) 在 P2 不现实 — 节点 schema 完全
 * 不同 (book:1 / entity:33 / scene:55 复合 ID vs R24 的 project_graph_node).
 * P2 这里用 SVG 简化渲染: book 中心 + 周边节点 (按类型着色), 边按关系
 * 着色 + evidence tooltip. 后续 P2.1 (UI 美化) 可以升级到 d3-force.
 */
import { getKnowledgeGraph, getDeepStudyNode } from "../api";
import type { KnowledgeGraphResponse, NodeDetailResponse, DeepStudyGraphNode } from "../types";
import { ShelfBreadcrumb } from "../components/shelf";

export function StudyBookGraphPage() {
  const { materialId } = useParams();
  const numericId = Number(materialId);
  const [graph, setGraph] = useState<KnowledgeGraphResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<DeepStudyGraphNode | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!numericId) return;
    let cancelled = false;
    setLoading(true);
    getKnowledgeGraph(numericId)
      .then((g) => { if (!cancelled) setGraph(g); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [numericId]);

  // 点节点拉详情
  useEffect(() => {
    if (!selectedNode || !numericId) { setNodeDetail(null); return; }
    let cancelled = false;
    getDeepStudyNode(numericId, selectedNode.id)
      .then((d) => { if (!cancelled) setNodeDetail(d); })
      .catch(() => { if (!cancelled) setNodeDetail(null); });
    return () => { cancelled = true; };
  }, [selectedNode, numericId]);

  if (!numericId) {
    return (
      <div className="page-empty">
        <ShelfBreadcrumb
          backTo="/study/library"
          backLabel="返回拆书书架"
          items={[{ label: "知识网络" }]}
        />
        <p className="muted">缺少 materialId 参数。</p>
      </div>
    );
  }

  return (
    <div className="page-body" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ShelfBreadcrumb
        backTo="/study/library"
        backLabel="返回拆书书架"
        items={[
          { label: "拆书书架", to: "/study/library" },
          { label: graph?.book?.title ?? `材料 #${numericId}` },
          { label: "知识网络" },
        ]}
      />
      <div className="subheader">
        <h2 className="serif">🌐 {graph?.book?.title ?? `材料 #${numericId}`} · 知识网络</h2>
        {graph?.stats && (
          <span className="meta">
            {graph.stats.nodes} 节点 · {graph.stats.edges} 边
            {Object.keys(graph.stats.by_type).length > 0 && (
              <> · 类型: {Object.entries(graph.stats.by_type).map(([k, v]) => `${k}=${v}`).join(", ")}</>
            )}
          </span>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="muted small" style={{ padding: 24 }}>加载知识网络…</div>
      ) : !graph ? (
        <div className="muted small" style={{ padding: 24 }}>未拿到网络数据。</div>
      ) : graph.nodes.length === 0 ? (
        <div className="empty-large">
          <div className="empty-large-glyph">🌐</div>
          <h3>这本书还没产生知识节点</h3>
          <p>回到 <a href="/study/library">拆书书架</a>, 选这本书 → ShelfDetailPanel → 启动 DeepStudy (mode: full)。<br />
          跑完后这里的网络会自动填上 Entity / SceneBeat / Foreshadow / Behavior / Technique 节点。</p>
        </div>
      ) : (
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 320px", minHeight: 0 }}>
          <GraphCanvas graph={graph} selectedNodeId={selectedNode?.id ?? null} onSelect={setSelectedNode} />
          <NodeDetailPanel detail={nodeDetail} />
        </div>
      )}
    </div>
  );
}

// ----- 简易 SVG 图谱渲染 (P2) -----------------------------------------
const TYPE_COLOR: Record<string, string> = {
  book:        "#d6a64e",  // gold (中心)
  entity:      "#3a6ea5",  // blue
  character:   "#5d9c5d",  // green
  scene:       "#a078c8",  // purple
  scene_beat:  "#a078c8",
  relationship:"#6e7681",  // gray
  foreshadow:  "#c45858",  // red
  behavior:    "#d6a64e",  // gold
  technique:   "#3a6ea5",  // blue
};
function nodeColor(type: string): string {
  return TYPE_COLOR[type] ?? "#6e7681";
}

function GraphCanvas({ graph, selectedNodeId, onSelect }: {
  graph: KnowledgeGraphResponse;
  selectedNodeId: string | null;
  onSelect: (n: DeepStudyGraphNode) => void;
}) {
  // 找 book 中心节点, 其它节点按书中心放射状铺开 (简单布局, P2 不上 d3-force)
  const W = 800, H = 600;
  const cx = W / 2, cy = H / 2;
  const bookNode = graph.nodes.find((n) => n.id.startsWith("book:"));
  const otherNodes = graph.nodes.filter((n) => n !== bookNode);

  // 节点位置: book 中心, 其它按类型分组扇区
  const byType: Record<string, typeof otherNodes> = {};
  for (const n of otherNodes) {
    const t = n.type || "other";
    (byType[t] ??= []).push(n);
  }
  const sectorTypes = Object.keys(byType);
  const sectorAngle = (Math.PI * 2) / Math.max(sectorTypes.length, 1);
  const positions: Record<string, { x: number; y: number; n: DeepStudyGraphNode }> = {};
  if (bookNode) positions[bookNode.id] = { x: cx, y: cy, n: bookNode };
  for (let s = 0; s < sectorTypes.length; s++) {
    const t = sectorTypes[s];
    const list = byType[t];
    const baseAngle = s * sectorAngle - Math.PI / 2;
    for (let i = 0; i < list.length; i++) {
      const r = 200 + (i % 3) * 50;
      const a = baseAngle + (i - list.length / 2) * 0.08;
      positions[list[i].id] = {
        x: cx + r * Math.cos(a),
        y: cy + r * Math.sin(a),
        n: list[i],
      };
    }
  }

  return (
    <div style={{ overflow: "auto", padding: 16, background: "var(--bg-base)" }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: "100%", height: "auto" }}>
        {/* 边 */}
        {graph.edges.map((e) => {
          const a = positions[e.source];
          const b = positions[e.target];
          if (!a || !b) return null;
          return (
            <line
              key={e.id}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="var(--accent-line, #4a4a52)"
              strokeWidth={Math.max(1, e.weight * 3)}
              opacity={0.6}
            >
              <title>{e.label || e.type}{e.evidence ? ` · ${e.evidence.slice(0, 80)}` : ""}</title>
            </line>
          );
        })}
        {/* 节点 */}
        {Object.values(positions).map(({ x, y, n }) => {
          const r = n.id === bookNode?.id ? 28 : 12 + Math.min(8, (n.size ?? 10) / 5);
          const fill = nodeColor(n.type);
          const isSel = n.id === selectedNodeId;
          return (
            <g
              key={n.id}
              transform={`translate(${x}, ${y})`}
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(n)}
            >
              <circle
                r={r}
                fill={fill}
                stroke={isSel ? "#fff" : "rgba(0,0,0,0.4)"}
                strokeWidth={isSel ? 3 : 1}
                opacity={n.id === bookNode?.id ? 1 : 0.45 + 0.55 * n.score}
              />
              <text
                y={r + 12}
                textAnchor="middle"
                fontSize={n.id === bookNode?.id ? 13 : 10}
                fill="var(--text-primary, #e6e6e6)"
                style={{ pointerEvents: "none" }}
              >
                {n.label.length > 14 ? n.label.slice(0, 14) + "…" : n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function NodeDetailPanel({ detail }: { detail: NodeDetailResponse | null }) {
  if (!detail) {
    return (
      <div style={{ padding: 16, borderLeft: "1px solid var(--accent-line-soft)", color: "var(--text-muted)", fontSize: 12 }}>
        点中间的节点查看详情 (entity / scene / foreshadow / behavior / technique 等).
      </div>
    );
  }
  return (
    <div style={{ padding: 16, borderLeft: "1px solid var(--accent-line-soft)", overflow: "auto", fontSize: 12 }}>
      <div style={{ marginBottom: 8 }}>
        <span className="pill tiny">{detail.type}</span>
        <b style={{ marginLeft: 6 }}>{detail.label}</b>
      </div>
      {Object.keys(detail.profile).length > 0 && (
        <Section title="Profile">
          <pre style={{ fontSize: 11, background: "var(--bg-elevated)", padding: 8, borderRadius: 4, maxHeight: 200, overflow: "auto" }}>
            {JSON.stringify(detail.profile, null, 2)}
          </pre>
        </Section>
      )}
      {detail.mentions.length > 0 && <Section title={`Mentions (${detail.mentions.length})`}><List items={detail.mentions.slice(0, 5).map((m: any) => m.quote ?? m.text ?? JSON.stringify(m))} /></Section>}
      {detail.relationships.length > 0 && <Section title={`Relationships (${detail.relationships.length})`}><List items={detail.relationships.slice(0, 5).map((r: any) => `${r.relation ?? r.relation_label ?? "?"} → ${r.target_label ?? r.target ?? ""}`)} /></Section>}
      {detail.scene_beats.length > 0 && <Section title={`Scene Beats (${detail.scene_beats.length})`}><List items={detail.scene_beats.slice(0, 3).map((s: any) => s.action ?? s.name ?? JSON.stringify(s))} /></Section>}
      {detail.foreshadows.length > 0 && <Section title={`Foreshadows (${detail.foreshadows.length})`}><List items={detail.foreshadows.slice(0, 3).map((f: any) => f.name ?? f.summary ?? JSON.stringify(f))} /></Section>}
      {detail.behavior_patterns.length > 0 && <Section title={`Behavior Patterns (${detail.behavior_patterns.length})`}><List items={detail.behavior_patterns.slice(0, 3).map((b: any) => b.name ?? JSON.stringify(b))} /></Section>}
      {detail.techniques.length > 0 && <Section title={`Techniques (${detail.techniques.length})`}><List items={detail.techniques.slice(0, 3).map((t: any) => t.name ?? t.technique_type ?? JSON.stringify(t))} /></Section>}
      {detail.agent_steps.length > 0 && <Section title={`Agent Steps (${detail.agent_steps.length})`}><List items={detail.agent_steps.slice(0, 5).map((s: any) => `${s.agent ?? "?"} · ${s.step ?? ""} · ${s.status ?? ""}`)} /></Section>}
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
function List({ items }: { items: any[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {items.map((it, i) => <li key={i} style={{ marginBottom: 2 }}>{String(it)}</li>)}
    </ul>
  );
}
