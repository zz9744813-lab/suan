/**
 * DiscussionPage — 圆桌讨论 (P0-FEAT-1)
 *
 * 布局:
 *   顶部: 议题输入 + 参与者多选 + "开始讨论" 按钮
 *   左下: 历史讨论列表 (可点开看历史 transcript)
 *   右下: 当前讨论 transcript (流式展示, 跑完就是 N+1 张卡 + 总编综合)
 *
 * 注意:
 *   - 跑一次讨论 30s~60s, 用 polling 拿最新状态 (后端目前没做流式, 是
 *     一次性 POST 拿回完整 transcript)
 *   - 后端是 SQLite + 同步实现, 跑的时候按钮 disable + 提示剩余时间
 */
import { useEffect, useState } from "react";
import {
  runDiscussion, listDiscussionSessions, getDiscussionSession,
} from "../api";
import {
  DISCUSSION_PARTICIPANTS, type DiscussionParticipantKey,
  type DiscussionSession, type DiscussionTurn,
} from "../types";
import { useProjectStore } from "../stores/projectStore";
import "./DiscussionPage.css";

const STORAGE_KEY = "noverlforge.discussion.draft.v1";

type Draft = { topic: string; participants: DiscussionParticipantKey[] };

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Draft;
  } catch {}
  return { topic: "", participants: ["planner", "critic", "continuity"] };
}

function saveDraft(d: Draft) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(d)); } catch {}
}

export function DiscussionPage() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [history, setHistory] = useState<DiscussionSession[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { saveDraft(draft); }, [draft]);
  useEffect(() => { refreshHistory(); }, []);

  async function refreshHistory() {
    try {
      const list = await listDiscussionSessions();
      setHistory(list);
    } catch (e: any) { /* silent */ }
  }

  async function start() {
    if (draft.topic.trim().length < 2) {
      setError("议题至少 2 个字");
      return;
    }
    if (draft.participants.length === 0) {
      setError("至少选一位参与者");
      return;
    }
    setError(null);
    setBusy(true);
    setActiveId(null);
    try {
      const sess = await runDiscussion({
        project_id: currentProjectId ?? undefined,
        topic: draft.topic.trim(),
        participants: draft.participants,
      });
      setActiveId(sess.id);
      await refreshHistory();
    } catch (e: any) {
      setError(e.message ?? "讨论失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page discussion-page">
      <div className="subheader">
        <h2 className="serif">讨论室</h2>
        <span className="muted small">让策划 / 主笔 / 审稿 / 连戏 / 记忆官围着议题各抒己见, 总编收尾</span>
      </div>

      <div className="discussion-grid">
        {/* ====== 左侧: 议题输入 + 参与者 ====== */}
        <div className="discussion-composer card">
          <h3>新讨论</h3>
          <div className="field">
            <label>议题</label>
            <textarea
              value={draft.topic}
              onChange={(e) => setDraft({ ...draft, topic: e.target.value })}
              placeholder="例: 主角林萧被逐出师门后, 应该走复仇线还是隐居修炼线?"
              rows={3}
              disabled={busy}
            />
          </div>
          <div className="field">
            <label>参与者 (选 1~5 位)</label>
            <div className="participant-toggles">
              {DISCUSSION_PARTICIPANTS.map((p) => {
                const on = draft.participants.includes(p.key);
                return (
                  <button
                    key={p.key}
                    className={`participant-toggle ${on ? "on" : ""}`}
                    onClick={() => {
                      if (busy) return;
                      const next = on
                        ? draft.participants.filter((k) => k !== p.key)
                        : [...draft.participants, p.key];
                      setDraft({ ...draft, participants: next });
                    }}
                    disabled={busy}
                    title={`${p.label} (${p.role})`}
                  >
                    <span className="emoji">{p.emoji}</span>
                    <span className="label">{p.label}</span>
                    <span className={`check ${on ? "on" : ""}`}>{on ? "✓" : ""}</span>
                  </button>
                );
              })}
            </div>
          </div>
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <span className="muted small">
              {busy
                ? "讨论进行中, 通常需要 30~60s ..."
                : "每次讨论 1+N 次 LLM 调用, 约 $0.01~0.05"}
            </span>
            <button
              className="primary"
              onClick={start}
              disabled={busy || draft.participants.length === 0}
            >
              {busy ? <><span className="spinner" />讨论中...</> : "开始讨论"}
            </button>
          </div>
        </div>

        {/* ====== 右侧: Transcript ====== */}
        <div className="discussion-transcript">
          {activeId === null && <EmptyTranscript />}
          {activeId !== null && (
            <TranscriptView
              sessionId={activeId}
              onReload={refreshHistory}
            />
          )}
        </div>

        {/* ====== 底部: 历史 ====== */}
        <div className="discussion-history card">
          <h3>历史讨论 ({history.length})</h3>
          {history.length === 0 ? (
            <div className="muted small">还没有讨论记录。</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>议题</th>
                  <th>参与者</th>
                  <th>状态</th>
                  <th style={{ textAlign: "right" }}>费用</th>
                  <th>时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className={activeId === h.id ? "active" : ""}>
                    <td className="topic-cell">{h.topic}</td>
                    <td className="muted small">{h.participants.length}位</td>
                    <td>
                      <span className={`pill ${h.status}`}>{statusLabel(h.status)}</span>
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      ${h.total_cost_usd.toFixed(4)}
                    </td>
                    <td className="muted tiny">
                      {new Date(h.created_at).toLocaleString("zh-CN")}
                    </td>
                    <td>
                      <button
                        className="link"
                        onClick={() => setActiveId(h.id)}
                      >
                        {activeId === h.id ? "已展开" : "查看"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyTranscript() {
  return (
    <div className="card empty-transcript">
      <div className="empty-icon">💬</div>
      <div className="muted">在左侧写议题, 选 1~5 位参与者, 然后点"开始讨论"。</div>
      <div className="muted small">参与者会并行(或顺序)发言, 最后由总编综合。</div>
    </div>
  );
}

function TranscriptView({
  sessionId, onReload,
}: { sessionId: number; onReload: () => void }) {
  const [sess, setSess] = useState<DiscussionSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await getDiscussionSession(sessionId);
        if (!cancelled) {
          setSess(s);
          setLoading(false);
        }
        if (s.status === "running") onReload();
      } catch {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const t = window.setInterval(load, 2000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, [sessionId, onReload]);

  if (loading || !sess) {
    return (
      <div className="card">
        <div className="muted"><span className="spinner" /> 加载讨论…</div>
      </div>
    );
  }

  return (
    <div className="transcript">
      <div className="transcript-header card">
        <div>
          <h3 className="serif">议题</h3>
          <div className="transcript-topic">{sess.topic}</div>
        </div>
        <div className="transcript-stats">
          <span className={`pill ${sess.status}`}>{statusLabel(sess.status)}</span>
          <span className="mono small">${sess.total_cost_usd.toFixed(4)}</span>
          <span className="mono small">
            {(sess.total_input_tokens + sess.total_output_tokens).toLocaleString()} tok
          </span>
          <span className="muted small">
            {sess.turns.length} turn
          </span>
        </div>
      </div>

      {sess.error && <div className="error-card">⚠ {sess.error}</div>}

      <div className="turns">
        {sess.turns.map((t) => (
          <TurnCard key={t.id} turn={t} />
        ))}
      </div>
    </div>
  );
}

function TurnCard({ turn }: { turn: DiscussionTurn }) {
  const isSynth = turn.kind === "synthesis";
  const meta = DISCUSSION_PARTICIPANTS.find((p) => p.label === turn.role_label);

  return (
    <div className={`turn-card ${isSynth ? "synthesis" : "participant"} ${turn.error ? "has-error" : ""}`}>
      <div className="turn-head">
        <div className="turn-avatar">
          {isSynth ? "★" : (meta?.emoji ?? "·")}
        </div>
        <div className="turn-meta">
          <div className="turn-name">
            {turn.role_label}
            {isSynth && <span className="badge">综合</span>}
            {turn.error && <span className="badge bad">失败</span>}
          </div>
          <div className="turn-stats muted tiny">
            {turn.duration_ms}ms · {turn.input_tokens}+{turn.output_tokens} tok · ${turn.cost_usd.toFixed(4)}
            · {new Date(turn.created_at).toLocaleTimeString("zh-CN")}
          </div>
        </div>
      </div>

      {turn.error ? (
        <div className="turn-error">{turn.error}</div>
      ) : (
        <>
          <div className="turn-content">{turn.content || "(空内容)"}</div>
          {turn.parsed && !isSynth && (turn.parsed.key_points?.length || turn.parsed.concerns?.length) ? (
            <div className="turn-details">
              {turn.parsed.key_points && turn.parsed.key_points.length > 0 && (
                <div className="detail-block">
                  <div className="detail-title">关键观点</div>
                  <ul>{turn.parsed.key_points.map((kp, i) => <li key={i}>{kp}</li>)}</ul>
                </div>
              )}
              {turn.parsed.concerns && turn.parsed.concerns.length > 0 && (
                <div className="detail-block">
                  <div className="detail-title">担忧</div>
                  <ul>{turn.parsed.concerns.map((c, i) => <li key={i}>{c}</li>)}</ul>
                </div>
              )}
            </div>
          ) : null}
          {isSynth && turn.parsed && (
            <div className="turn-details synthesis-details">
              {turn.parsed.summary && (
                <div className="detail-block">
                  <div className="detail-title">概述</div>
                  <div>{turn.parsed.summary}</div>
                </div>
              )}
              {turn.parsed.agreement && turn.parsed.agreement.length > 0 && (
                <div className="detail-block">
                  <div className="detail-title">各方一致</div>
                  <ul>{turn.parsed.agreement.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </div>
              )}
              {turn.parsed.tension && turn.parsed.tension.length > 0 && (
                <div className="detail-block">
                  <div className="detail-title">分歧</div>
                  <ul>{turn.parsed.tension.map((t, i) => <li key={i}>{t}</li>)}</ul>
                </div>
              )}
              {turn.parsed.next_actions && turn.parsed.next_actions.length > 0 && (
                <div className="detail-block">
                  <div className="detail-title">下一步动作</div>
                  <ul>{turn.parsed.next_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function statusLabel(s: string): string {
  switch (s) {
    case "running": return "进行中";
    case "succeeded": return "完成";
    case "partial": return "部分";
    case "failed": return "失败";
    default: return s;
  }
}
