/**
 * AutomationAuditPage — 自动化审计页面 (NF2 阶段6)
 *
 * 统一看板: 模型选择、Prompt填充、评论评审、讨论裁决
 * 按事件类型筛选
 * 时间线展示
 * 调用 /api/audit/logs 和 /api/audit/stats/by-event
 */
import { useCallback, useEffect, useState } from "react";
import { PageTopbar } from "../components/layout/PageTopbar";
import { listAuditLogs, getAuditStatsByEvent } from "../api";

type AuditLog = {
  id: number;
  event_type: string;
  actor_type: string;
  actor_key: string | null;
  project_id: number | null;
  chapter_id: number | null;
  action: string;
  details: Record<string, unknown> | null;
  created_at: string;
};

const EVENT_TYPES = [
  { key: "", label: "全部" },
  { key: "model_switch", label: "模型切换" },
  { key: "prompt_binding_change", label: "Prompt绑定" },
  { key: "review_action", label: "评论评审" },
  { key: "discussion_created", label: "讨论创建" },
  { key: "settings_change", label: "设置变更" },
  { key: "agent_task_completed", label: "任务完成" },
  { key: "agent_task_failed", label: "任务失败" },
];

const EVENT_COLORS: Record<string, string> = {
  model_switch: "#2196f3",
  prompt_binding_change: "#9c27b0",
  review_action: "#ff9800",
  discussion_created: "#4caf50",
  settings_change: "#607d8b",
  agent_task_completed: "#43a047",
  agent_task_failed: "#e53935",
};

function normalizeStats(raw: any): Record<string, number> {
  const source = raw?.by_event ?? raw?.counts ?? raw;
  const entries = Array.isArray(source)
    ? source.map((item) => [
        String(item?.event_type ?? item?.key ?? item?.name ?? ""),
        item?.count ?? item?.total ?? item?.value,
      ])
    : Object.entries(source ?? {});

  return entries.reduce<Record<string, number>>((acc, [key, value]) => {
    const count =
      typeof value === "number"
        ? value
        : value && typeof value === "object"
          ? Number((value as any).count ?? (value as any).total ?? (value as any).value)
          : Number(value);
    if (key && Number.isFinite(count)) acc[key] = count;
    return acc;
  }, {});
}

export function AutomationAuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [projectId, setProjectId] = useState<number | undefined>(undefined);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filter) params.event_type = filter;
      if (projectId) params.project_id = String(projectId);
      const [l, s] = await Promise.all([
        listAuditLogs(params),
        getAuditStatsByEvent(projectId ? { project_id: projectId } : undefined),
      ]);
      setLogs(Array.isArray(l) ? l : l?.items ?? []);
      setStats(normalizeStats(s));
    } catch { /* */ }
    setLoading(false);
  }, [filter, projectId]);

  useEffect(() => { load(); }, [load]);

  const eventColor = (et: string) => EVENT_COLORS[et] || "#bdbdbd";

  return (
    <div>
      <PageTopbar
        title="自动化审计"
        icon="🔍"
        subtitle="模型选择、Prompt填充、评论评审、讨论裁决的统一看板"
        actions={[
          { label: "刷新", variant: "ghost", onClick: load },
        ]}
      />

      <div style={{ padding: "16px 24px" }}>
        {/* Stats cards */}
        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          {Object.entries(stats).map(([key, count]) => (
            <div
              key={key}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "1px solid var(--border, #ddd)",
                minWidth: 120,
              }}
            >
              <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{key}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: eventColor(key) }}>{count}</div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
          {EVENT_TYPES.map((et) => (
            <button
              key={et.key}
              className={filter === et.key ? "primary" : ""}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 4 }}
              onClick={() => setFilter(et.key)}
            >
              {et.label}
            </button>
          ))}
          <div style={{ marginLeft: 8, display: "flex", alignItems: "center", gap: 4 }}>
            <span className="muted" style={{ fontSize: 11 }}>项目ID:</span>
            <input
              className="input"
              type="number"
              style={{ width: 80, fontSize: 12 }}
              value={projectId ?? ""}
              onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)}
              placeholder="全部"
            />
          </div>
        </div>

        {/* Timeline */}
        {loading ? (
          <div className="muted">加载中…</div>
        ) : logs.length === 0 ? (
          <div className="muted">暂无审计记录</div>
        ) : (
          <div style={{ position: "relative", paddingLeft: 16 }}>
            {logs.map((log, i) => (
              <div
                key={log.id ?? i}
                style={{
                  position: "relative",
                  paddingBottom: 12,
                  borderLeft: "2px solid var(--border, #ddd)",
                  marginLeft: -6,
                  paddingLeft: 18,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    left: -6,
                    top: 4,
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: eventColor(log.event_type),
                    border: "2px solid var(--bg-card, #fff)",
                  }}
                />
                <div style={{ fontSize: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontWeight: 600, color: eventColor(log.event_type) }}>
                      {log.event_type}
                    </span>
                    {log.actor_key && (
                      <span className="pill" style={{ fontSize: 10 }}>{log.actor_key}</span>
                    )}
                    <span className="muted" style={{ fontSize: 10, marginLeft: "auto" }}>
                      {log.created_at ? new Date(log.created_at).toLocaleString("zh-CN") : ""}
                    </span>
                  </div>
                  <div style={{ color: "var(--text-secondary, #666)", lineHeight: 1.4 }}>
                    {log.action || "—"}
                  </div>
                  {(log.project_id || log.chapter_id) && (
                    <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>
                      {log.project_id && `项目 #${log.project_id}`}
                      {log.chapter_id && ` · 章节 #${log.chapter_id}`}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
