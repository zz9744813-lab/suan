/**
 * DiscussionPage — Agent 自动讨论留痕 + Skill 沉淀 (P9)
 *
 * 三栏布局:
 *   左侧: 讨论线程队列 (搜索 / 状态筛选 / 线程卡片列表)
 *   中间: Agent 留痕时间线 (问题来源 / 阶段进度 / 发言气泡)
 *   右侧: 成果面板 (最终结论 / 修改任务 / Skill 草案 / 回收倒计时)
 *
 * 替代旧版"用户输入议题 + 选择参与者 + 点击开始讨论"的手动模式。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  listDiscussionThreads, getDiscussionStats, getDiscussionThreadDetail,
  createDiscussionThread, runDiscussionThread, solidifySkill,
  extendRecycle, recycleNow, restoreThread,
  type DiscussionStats, type ThreadSummary, type ThreadDetail,
  type DiscussionMsgRead, type SkillDraftRead,
} from "../api";
import { useProjectStore } from "../stores/projectStore";
import "./DiscussionPage.css";

// --- status/issue/risk labels ---
const STATUS_LABELS: Record<string, string> = {
  pending_discussion: "待讨论", discussing: "讨论中", converged: "已收敛",
  rewrite_created: "已创建修改", skill_draft_created: "Skill 草案",
  archived: "等待回收", recycled: "已回收", ignored: "忽略",
  failed: "失败",
};
const STATUS_COLORS: Record<string, string> = {
  pending_discussion: "#60a5fa", discussing: "#3b82f6", converged: "#4ade80",
  rewrite_created: "#fbbf24", skill_draft_created: "#a78bfa",
  archived: "#9ca3af", recycled: "#6b7280", ignored: "#6b7280", failed: "#f87171",
};
const RISK_COLORS: Record<string, string> = {
  low: "#4ade80", medium: "#fbbf24", high: "#f97316", critical: "#ef4444",
};
const AGENT_COLORS: Record<string, string> = {
  planner: "#3b82f6", drafter: "#f97316", critic: "#8b5cf6",
  continuity: "#22c55e", chief: "#1f2937", skill_builder: "#6366f1",
  memory: "#06b6d4",
};
const AGENT_LABELS: Record<string, string> = {
  planner: "策划", drafter: "主笔", critic: "审稿",
  continuity: "连戏", chief: "总编", skill_builder: "SkillBuilder",
  memory: "记忆官",
};

// --- format helpers ---
function fmtTime(sec: number): string {
  if (sec < 3600) return `${Math.floor(sec / 60)}分钟`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}小时`;
  return `${(sec / 86400).toFixed(1)}天`;
}

function fmtRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

// ===========================================================================
export function DiscussionPage() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [stats, setStats] = useState<DiscussionStats | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("active");
  const [searchQ, setSearchQ] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // --- fetch ---
  const refreshList = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([
        getDiscussionStats(projectId ?? undefined),
        listDiscussionThreads({ project_id: projectId ?? undefined, status: filterStatus === "active" ? undefined : filterStatus, q: searchQ || undefined }),
      ]);
      setStats(s);
      setThreads(d.items);
      setTotal(d.total);
    } catch { /* silent */ }
  }, [projectId, filterStatus, searchQ]);

  const refreshDetail = useCallback(async () => {
    if (!selectedId) { setDetail(null); return; }
    try {
      const d = await getDiscussionThreadDetail(selectedId);
      setDetail(d);
    } catch { /* silent */ }
  }, [selectedId]);

  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => { refreshDetail(); }, [refreshDetail]);

  // polling for discussing threads
  useEffect(() => {
    const hasActive = threads.some((t) => t.status === "discussing");
    if (!hasActive) return;
    const timer = setInterval(() => { refreshList(); refreshDetail(); }, 5000);
    return () => clearInterval(timer);
  }, [threads, refreshList, refreshDetail]);

  // --- actions ---
  async function handleCreate(title: string, issueType: string, riskLevel: string, note: string) {
    try {
      const t = await createDiscussionThread({
        project_id: projectId ?? undefined, title, issue_type: issueType,
        risk_level: riskLevel, user_note: note || undefined,
      });
      setShowCreate(false);
      setSelectedId(t.id);
      refreshList();
    } catch (e: any) { alert(e.message ?? "创建失败"); }
  }

  async function handleRun(id: number) {
    try { await runDiscussionThread(id); refreshList(); refreshDetail(); }
    catch (e: any) { alert(e.message ?? "启动失败"); }
  }

  async function handleSolidify(threadId: number, draftId: number) {
    try { await solidifySkill(threadId, draftId); refreshDetail(); }
    catch (e: any) { alert(e.message ?? "固化失败"); }
  }

  async function handleExtend(threadId: number, days: number) {
    try { await extendRecycle(threadId, days); refreshDetail(); }
    catch (e: any) { alert(e.message ?? "延长失败"); }
  }

  async function handleRecycleNow(threadId: number) {
    if (!confirm("确定立即回收？原始讨论将被压缩。")) return;
    try { await recycleNow(threadId); refreshList(); refreshDetail(); }
    catch (e: any) { alert(e.message ?? "回收失败"); }
  }

  async function handleRestore(threadId: number) {
    try { await restoreThread(threadId); refreshDetail(); refreshList(); }
    catch (e: any) { alert(e.message ?? "恢复失败"); }
  }

  return (
    <div className="page disc-page">
      {/* LEFT SIDEBAR */}
      <aside className="disc-sidebar">
        <div className="disc-sidebar-head">
          <h2 className="serif">讨论室</h2>
          <button className="btn-sm" onClick={() => setShowCreate(true)} title="手动补充问题">+ 补充</button>
        </div>

        {stats && (
          <div className="disc-stats-bar">
            <span className="stat" style={{ color: "#3b82f6" }}>进行 {stats.active_count}</span>
            <span className="stat" style={{ color: "#4ade80" }}>收敛 {stats.converged_count}</span>
            <span className="stat" style={{ color: "#a78bfa" }}>待Skill {stats.pending_skill_count}</span>
            {stats.recycle_soon_count > 0 && (
              <span className="stat" style={{ color: "#f97316" }}>即将回收 {stats.recycle_soon_count}</span>
            )}
          </div>
        )}

        <input
          className="disc-search"
          type="text" placeholder="搜索问题、章节、Agent..."
          value={searchQ} onChange={(e) => setSearchQ(e.target.value)}
        />

        <div className="disc-filter-tabs">
          {[
            { key: "active", label: "活跃" },
            { key: "converged", label: "已收敛" },
            { key: "skill_draft_created", label: "待Skill" },
            { key: "archived", label: "等待回收" },
            { key: "recycled", label: "冷存档" },
          ].map((f) => (
            <button key={f.key}
              className={`filter-tab ${filterStatus === f.key ? "on" : ""}`}
              onClick={() => setFilterStatus(f.key)}
            >{f.label}</button>
          ))}
        </div>

        <div className="disc-thread-list">
          {threads.length === 0 && <div className="disc-empty">暂无讨论线程</div>}
          {threads.map((t) => (
            <div
              key={t.id}
              className={`disc-thread-card ${selectedId === t.id ? "selected" : ""}`}
              onClick={() => setSelectedId(t.id)}
            >
              <div className="dtc-head">
                <span className="dtc-risk" style={{ background: RISK_COLORS[t.risk_level] || "#9ca3af" }} />
                <span className="dtc-title">{t.title}</span>
              </div>
              <div className="dtc-meta">
                <span className="dtc-status" style={{ color: STATUS_COLORS[t.status] || "#9ca3af" }}>
                  {STATUS_LABELS[t.status] || t.status}
                </span>
                <span className="dtc-source">{t.source_type}</span>
                <span className="dtc-msgs">{t.message_count}条</span>
                {t.remaining_seconds != null && t.remaining_seconds > 0 && (
                  <span className="dtc-countdown">{fmtTime(t.remaining_seconds)}</span>
                )}
              </div>
              <div className="dtc-badges">
                {t.has_rewrite_task && <span className="badge-sm badge-rewrite">修改</span>}
                {t.has_skill_draft && <span className="badge-sm badge-skill">Skill</span>}
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* CENTER TIMELINE */}
      <main className="disc-timeline">
        {!detail ? (
          <div className="disc-timeline-empty">
            <div className="empty-icon-lg">🔍</div>
            <div>选择左侧讨论线程查看详情</div>
            <div className="muted small">Agent 发现问题后会自动创建讨论</div>
          </div>
        ) : (
          <div className="disc-timeline-inner">
            {/* header */}
            <div className="dt-header">
              <div>
                <h3 className="serif">{detail.title}</h3>
                <div className="dt-meta-row">
                  <span className="dt-status-pill" style={{ background: STATUS_COLORS[detail.status] || "#9ca3af", color: "#fff" }}>
                    {STATUS_LABELS[detail.status] || detail.status}
                  </span>
                  <span className="dt-risk-pill" style={{ background: RISK_COLORS[detail.risk_level] || "#9ca3af", color: "#fff" }}>
                    {detail.risk_level}
                  </span>
                  <span className="muted small">来源: {detail.source_type}</span>
                  <span className="muted small">类型: {detail.issue_type}</span>
                </div>
              </div>
              {detail.status === "pending_discussion" && (
                <button className="btn-primary" onClick={() => handleRun(detail.id)}>▶ 开始讨论</button>
              )}
              {detail.status === "failed" && (
                <button className="btn-primary" onClick={() => handleRun(detail.id)}>↻ 重试</button>
              )}
            </div>

            {/* issue sources */}
            {detail.issue_sources.length > 0 && (
              <div className="dt-sources">
                <h4>问题来源</h4>
                {detail.issue_sources.map((s) => (
                  <div key={s.id} className="dt-source-item">
                    <span className="dt-source-type">{s.source_type}</span>
                    <span className="dt-source-severity" style={{ color: RISK_COLORS[s.severity] || "#9ca3af" }}>{s.severity}</span>
                    <div className="dt-source-summary">{s.problem_summary}</div>
                    {s.quote && <div className="dt-source-quote">"{s.quote}"</div>}
                  </div>
                ))}
              </div>
            )}

            {/* progress bar */}
            <div className="dt-progress">
              {["pending_discussion", "discussing", "converged", "rewrite_created", "skill_draft_created", "archived"].map((s, i) => {
                const currentIdx = ["pending_discussion", "discussing", "converged", "rewrite_created", "skill_draft_created", "archived"].indexOf(detail.status);
                const done = i <= currentIdx;
                return (
                  <div key={s} className={`dt-step ${done ? "done" : ""}`}>
                    <div className="dt-step-dot" />
                    <span>{STATUS_LABELS[s]}</span>
                  </div>
                );
              })}
            </div>

            {/* messages */}
            <div className="dt-messages">
              {detail.messages.length === 0 && detail.status === "pending_discussion" && (
                <div className="dt-no-msg">等待讨论启动...</div>
              )}
              {detail.messages.map((m) => (
                <MessageBubble key={m.id} msg={m} />
              ))}
            </div>
          </div>
        )}
      </main>

      {/* RIGHT RESULT PANEL */}
      <aside className={`disc-result ${detail ? "open" : ""}`}>
        {!detail ? null : (
          <div className="disc-result-inner">
            {/* final decision */}
            {detail.final_decision && (
              <div className="dr-section">
                <h4>最终结论</h4>
                <div className={`dr-decision ${detail.final_decision}`}>
                  {detail.final_decision === "modify" ? "✓ 需要修改" :
                   detail.final_decision === "no_modify" ? "✗ 无需修改" :
                   detail.final_decision === "defer" ? "⏸ 暂缓" : detail.final_decision}
                </div>
                {detail.final_reason && <p className="dr-reason">{detail.final_reason}</p>}
              </div>
            )}

            {/* rewrite task */}
            {detail.rewrite_task_id && (
              <div className="dr-section">
                <h4>修改任务</h4>
                <div className="dr-rewrite">任务 #{detail.rewrite_task_id}</div>
              </div>
            )}

            {/* skill draft */}
            {detail.skill_draft && (
              <div className="dr-section">
                <h4>Skill 草案</h4>
                <SkillDraftCard draft={detail.skill_draft}
                  onSolidify={() => handleSolidify(detail.id, detail.skill_draft!.id)}
                />
              </div>
            )}

            {/* recycle info */}
            <div className="dr-section">
              <h4>回收机制</h4>
              {detail.remaining_seconds != null && detail.remaining_seconds > 0 && (
                <div className="dr-countdown">
                  剩余 <b>{fmtTime(detail.remaining_seconds)}</b> 后自动回收
                </div>
              )}
              {detail.status === "recycled" && (
                <div className="dr-recycled">已回收 · 讨论已压缩归档</div>
              )}
            </div>

            {/* actions */}
            <div className="dr-actions">
              {detail.status === "recycled" && (
                <button className="btn-sm" onClick={() => handleRestore(detail.id)}>恢复原始讨论</button>
              )}
              {detail.remaining_seconds != null && detail.remaining_seconds > 0 && detail.status !== "recycled" && (
                <>
                  <button className="btn-sm" onClick={() => handleExtend(detail.id, 7)}>延长7天</button>
                  <button className="btn-sm btn-danger" onClick={() => handleRecycleNow(detail.id)}>立即回收</button>
                </>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* CREATE MODAL */}
      {showCreate && (
        <CreateModal
          onConfirm={handleCreate}
          onCancel={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}


// ===========================================================================
// Message Bubble
// ===========================================================================
function MessageBubble({ msg }: { msg: DiscussionMsgRead }) {
  const isChief = msg.speaker_role === "chief";
  const color = AGENT_COLORS[msg.speaker_role] || "#6b7280";
  const label = AGENT_LABELS[msg.speaker_role] || msg.speaker_role;
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`dt-msg ${isChief ? "chief" : ""} ${msg.error_message ? "has-error" : ""}`}>
      <div className="dt-msg-head">
        <div className="dt-msg-avatar" style={{ background: color }}>{label[0]}</div>
        <div className="dt-msg-meta">
          <div className="dt-msg-name" style={{ color }}>
            {label}
            {msg.accepted_by_chief && <span className="badge-sm badge-accepted">被采纳</span>}
          </div>
          <div className="dt-msg-info muted tiny">
            {fmtRelative(msg.created_at)}
            {msg.confidence != null && ` · 置信度 ${(msg.confidence * 100).toFixed(0)}%`}
            {msg.token_in + msg.token_out > 0 && ` · ${msg.token_in + msg.token_out}tok · $${msg.cost_usd.toFixed(4)}`}
          </div>
        </div>
      </div>

      {msg.error_message ? (
        <div className="dt-msg-error">⚠ {msg.error_message}</div>
      ) : (
        <div className="dt-msg-content">{msg.content}</div>
      )}

      {msg.decision_tags_json && msg.decision_tags_json.length > 0 && (
        <div className="dt-msg-tags">
          {msg.decision_tags_json.map((tag, i) => (
            <span key={i} className="chip">{tag}</span>
          ))}
        </div>
      )}

      {msg.evidence_json && (
        <button className="btn-link" onClick={() => setExpanded(!expanded)}>
          {expanded ? "收起证据" : "展开证据"}
        </button>
      )}
      {expanded && msg.evidence_json && (
        <pre className="dt-msg-evidence">{JSON.stringify(msg.evidence_json, null, 2)}</pre>
      )}
    </div>
  );
}


// ===========================================================================
// Skill Draft Card
// ===========================================================================
function SkillDraftCard({ draft, onSolidify }: { draft: SkillDraftRead; onSolidify: () => void }) {
  return (
    <div className="dr-skill-card">
      <div className="dr-skill-title">{draft.title}</div>
      <div className="dr-skill-type">{draft.skill_type} · {draft.status}</div>
      {draft.trigger_conditions_json.length > 0 && (
        <div className="dr-skill-section">
          <div className="dr-skill-label">触发条件</div>
          {draft.trigger_conditions_json.map((c, i) => <div key={i} className="dr-skill-item">· {c}</div>)}
        </div>
      )}
      {draft.applicable_scenes_json.length > 0 && (
        <div className="dr-skill-section">
          <div className="dr-skill-label">适用场景</div>
          {draft.applicable_scenes_json.map((s, i) => <div key={i} className="dr-skill-item">· {s}</div>)}
        </div>
      )}
      {draft.execution_template && (
        <div className="dr-skill-section">
          <div className="dr-skill-label">执行模板</div>
          <div className="dr-skill-exec">{draft.execution_template}</div>
        </div>
      )}
      {draft.anti_patterns_json.length > 0 && (
        <div className="dr-skill-section">
          <div className="dr-skill-label">反例</div>
          {draft.anti_patterns_json.map((a, i) => <div key={i} className="dr-skill-item anti">✗ {a}</div>)}
        </div>
      )}
      {draft.prompt_snippet && (
        <div className="dr-skill-section">
          <div className="dr-skill-label">Prompt 片段</div>
          <div className="dr-skill-prompt">{draft.prompt_snippet}</div>
        </div>
      )}
      {draft.applicable_agent_roles_json.length > 0 && (
        <div className="dr-skill-agents">
          适用: {draft.applicable_agent_roles_json.map((r) => AGENT_LABELS[r] || r).join(" / ")}
        </div>
      )}
      {draft.status === "draft" && (
        <button className="btn-sm btn-primary" onClick={onSolidify}>固化 Skill</button>
      )}
    </div>
  );
}


// ===========================================================================
// Create Modal
// ===========================================================================
function CreateModal({ onConfirm, onCancel }: {
  onConfirm: (title: string, issueType: string, riskLevel: string, note: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [issueType, setIssueType] = useState("other");
  const [riskLevel, setRiskLevel] = useState("medium");
  const [note, setNote] = useState("");

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <h3>手动补充问题</h3>
        <div className="field">
          <label>问题标题</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例：主角复仇动机断裂" />
        </div>
        <div className="field">
          <label>问题类型</label>
          <select value={issueType} onChange={(e) => setIssueType(e.target.value)}>
            <option value="logic">逻辑</option>
            <option value="character">人物</option>
            <option value="pacing">节奏</option>
            <option value="continuity">连续性</option>
            <option value="foreshadowing">伏笔</option>
            <option value="style">文风</option>
            <option value="commercial_hook">爽点</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div className="field">
          <label>风险等级</label>
          <select value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)}>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
            <option value="critical">严重</option>
          </select>
        </div>
        <div className="field">
          <label>补充说明</label>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="让 Agent 自己讨论这个问题" />
        </div>
        <div className="modal-actions">
          <button className="btn-sm" onClick={onCancel}>取消</button>
          <button className="btn-primary" disabled={title.trim().length < 2}
            onClick={() => onConfirm(title.trim(), issueType, riskLevel, note.trim())}
          >创建</button>
        </div>
      </div>
    </div>
  );
}
