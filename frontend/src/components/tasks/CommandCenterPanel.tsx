/**
 * CommandCenterPanel — P0 任务中控台
 *
 * 一个 dashboard 卡片, 用 GET /api/tasks/command-center 一次拿到 4 块数据:
 * - domains: 6 个 domain 汇总 (writing / deepstudy / discussion / memory / model / export)
 * - active: 当前活跃任务 (最多 5)
 * - needs_attention: 失败/需人工处理
 * - recent_completed: 最近 24h 完成
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCommandCenter } from "../../api";
import type { TaskCommandCenter, TaskDisplayItem } from "../../types";

const STATUS_LABEL: Record<string, string> = {
  idle: "空闲",
  running: "进行中",
  blocked: "等待",
  failed: "失败",
  succeeded: "今日已完成",
};

const STATUS_COLOR: Record<string, string> = {
  idle: "var(--text-muted)",
  running: "var(--accent, #1f80ff)",
  blocked: "var(--warning, #d58400)",
  failed: "var(--danger, #c45858)",
  succeeded: "var(--success, #4aa86a)",
};

const TASK_STATUS_COLOR: Record<string, string> = {
  running: "var(--accent, #1f80ff)",
  pending: "var(--warning, #d58400)",
  queued: "var(--warning, #d58400)",
  failed: "var(--danger, #c45858)",
  succeeded: "var(--success, #4aa86a)",
  cancelled: "var(--text-muted)",
};

function ProgressBar({ current, total }: { current: number; total: number }) {
  if (!total || total <= 0) return <div style={{ height: 4, background: "var(--bg-2)", borderRadius: 2 }} />;
  const pct = Math.min(100, Math.max(0, (current / total) * 100));
  return (
    <div style={{ height: 4, background: "var(--bg-2)", borderRadius: 2, overflow: "hidden", width: "100%" }}>
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          background: "var(--accent, #1f80ff)",
          transition: "width 200ms ease",
        }}
      />
    </div>
  );
}

function DomainCard({ d, onClickTask }: { d: TaskCommandCenter["domains"][number]; onClickTask: (id: number) => void }) {
  return (
    <div
      className="cc-domain-card"
      style={{
        border: "1px solid var(--border-color)",
        borderRadius: 6,
        padding: "10px 12px",
        background: "var(--bg-card)",
        display: "flex", flexDirection: "column", gap: 4,
        minHeight: 96,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{d.label}</div>
        <span style={{
          fontSize: 10, padding: "1px 6px", borderRadius: 3,
          background: STATUS_COLOR[d.status] + "22", color: STATUS_COLOR[d.status],
          fontWeight: 500,
        }}>
          {STATUS_LABEL[d.status] ?? d.status}
        </span>
      </div>
      <div style={{ display: "flex", gap: 12, fontSize: 14, fontWeight: 600, alignItems: "baseline" }}>
        <span>{d.running}</span>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>跑</span>
        <span style={{ fontSize: 14, color: d.pending > 0 ? STATUS_COLOR.blocked : "var(--text-muted)" }}>{d.pending}</span>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>等</span>
        <span style={{ fontSize: 14, color: d.failed > 0 ? STATUS_COLOR.failed : "var(--text-muted)" }}>{d.failed}</span>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>败</span>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          今日 +{d.succeeded_today}
        </span>
      </div>
      {d.current_task_id ? (
        <button
          onClick={() => onClickTask(d.current_task_id!)}
          title={d.current_title ?? ""}
          style={{
            background: "transparent", border: "none", color: "var(--text-primary)",
            textAlign: "left", padding: 0, fontSize: 12, cursor: "pointer",
            textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap",
          }}
        >
          📍 {d.current_title}
        </button>
      ) : (
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>—</div>
      )}
      {d.current_task_id ? (
        <ProgressBar current={d.progress_current} total={d.progress_total} />
      ) : null}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
        <span>${d.cost_today.toFixed(4)}</span>
        <span>{(d.tokens_today / 1000).toFixed(1)}k tok</span>
      </div>
    </div>
  );
}

function TaskRow({ t, onClick }: { t: TaskDisplayItem; onClick: (id: number) => void }) {
  const dotColor = TASK_STATUS_COLOR[t.status] ?? "var(--text-muted)";
  return (
    <button
      onClick={() => onClick(t.id)}
      style={{
        display: "flex", gap: 8, alignItems: "center", width: "100%",
        background: "transparent", border: "none", padding: "6px 8px",
        color: "var(--text-primary)", cursor: "pointer", textAlign: "left",
        fontSize: 12, borderRadius: 4,
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--bg-2)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor, flexShrink: 0 }} />
      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {t.title}
      </span>
      {t.progress_total > 0 && (
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
          {t.progress_current}/{t.progress_total}
        </span>
      )}
      <span style={{ fontSize: 10, color: "var(--text-muted)", minWidth: 50, textAlign: "right" }}>
        ${t.cost_usd.toFixed(4)}
      </span>
    </button>
  );
}

export function CommandCenterPanel(props: {
  pollIntervalMs?: number;
  collapsible?: boolean;
  initialCollapsed?: boolean;
  onTaskClick?: (id: number) => void;
}) {
  const { pollIntervalMs = 8000, onTaskClick } = props;
  const [data, setData] = useState<TaskCommandCenter | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const r = await getCommandCenter();
        if (!cancelled) {
          setData(r);
          setErr(null);
        }
      } catch (e: any) {
        if (!cancelled) setErr(e?.message ?? String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchOnce();
    const id = setInterval(fetchOnce, pollIntervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [pollIntervalMs]);

  const handleClick = (id: number) => {
    if (onTaskClick) onTaskClick(id);
    else navigate(`/tasks?task_id=${id}`);
  };

  if (loading && !data) {
    return (
      <div className="cc-panel" style={{ padding: 12, color: "var(--text-muted)", fontSize: 12 }}>
        任务中控台加载中…
      </div>
    );
  }
  if (err && !data) {
    return (
      <div className="cc-panel" style={{ padding: 12, color: "var(--danger)", fontSize: 12 }}>
        中控台拉取失败：{err}
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="cc-panel" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>⚙ 任务中控台</h3>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
          更新 {new Date(data.generated_at).toLocaleTimeString()}
        </span>
      </div>

      {/* 6 domain 卡 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8 }}>
        {data.domains.map((d) => (
          <DomainCard key={d.domain} d={d} onClickTask={handleClick} />
        ))}
      </div>

      {/* 三个列表: active / needs_attention / recent_completed */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <Section title={`运行中 (${data.active.length})`} empty="无" tone="running">
          {data.active.map((t) => <TaskRow key={t.id} t={t} onClick={handleClick} />)}
        </Section>
        <Section title={`需处理 (${data.needs_attention.length})`} empty="无" tone={data.needs_attention.length > 0 ? "failed" : "idle"}>
          {data.needs_attention.map((t) => <TaskRow key={t.id} t={t} onClick={handleClick} />)}
        </Section>
        <Section title={`最近 24h 完成 (${data.recent_completed.length})`} empty="无" tone="succeeded">
          {data.recent_completed.map((t) => <TaskRow key={t.id} t={t} onClick={handleClick} />)}
        </Section>
      </div>
    </div>
  );
}

function Section({ title, empty, tone, children }: { title: string; empty: string; tone: string; children: React.ReactNode }) {
  const isEmpty = (children as any[]).length === 0;
  return (
    <div style={{ border: "1px solid var(--border-color)", borderRadius: 6, background: "var(--bg-card)", overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 10px", borderBottom: "1px solid var(--border-color)" }}>
        <span style={{ fontSize: 12, fontWeight: 500 }}>{title}</span>
        <span style={{ fontSize: 10, color: STATUS_COLOR[tone] ?? "var(--text-muted)" }}>●</span>
      </div>
      <div style={{ padding: "4px 0", minHeight: 60, maxHeight: 220, overflowY: "auto" }}>
        {isEmpty ? (
          <div style={{ padding: "12px 8px", fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>{empty}</div>
        ) : children}
      </div>
    </div>
  );
}
