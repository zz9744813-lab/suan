type Props = {
  visible: boolean;
  event: any | null;
  onClose: () => void;
};

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleString("zh-CN", { hour12: false }); }
  catch { return iso; }
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 8, padding: "4px 0", borderBottom: "1px solid var(--line)" }}>
      <span style={{ fontSize: 11, color: "var(--muted)", minWidth: 80 }}>{label}</span>
      <span style={{ fontSize: 12, flex: 1, wordBreak: "break-all" }}>{value ?? "—"}</span>
    </div>
  );
}

export function EventDetailDrawer({ visible, event, onClose }: Props) {
  if (!visible || !event) return null;

  const ev = event;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: 360,
        height: "100vh",
        background: "var(--card, #1a1a1a)",
        borderLeft: "1px solid var(--line)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        boxShadow: "-4px 0 16px rgba(0,0,0,0.2)",
      }}
    >
      {/* 头部 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>事件 #{ev.id}</span>
        <button
          className="tiny"
          onClick={onClose}
          style={{ cursor: "pointer", background: "transparent", border: "1px solid var(--line)", borderRadius: 4, padding: "2px 8px" }}
        >
          关闭
        </button>
      </div>

      {/* 内容 */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
        <Row label="时间" value={ev.created_at ? formatTime(ev.created_at) : "—"} />
        <Row label="类型" value={ev.event_type} />
        <Row label="级别" value={ev.level ?? ev.status} />
        <Row label="Agent" value={ev.agent_role_key ?? ev.agent_name} />
        <Row label="Provider" value={ev.provider_name} />
        <Row label="Model" value={ev.model_name} />
        <Row label="任务 ID" value={ev.task_id} />
        <Row label="章节 ID" value={ev.chapter_id} />
        <Row label="项目 ID" value={ev.project_id} />
        <Row label="延迟" value={ev.latency_ms != null ? `${ev.latency_ms}ms` : "—"} />
        <Row label="Token" value={ev.total_tokens != null ? `${ev.input_tokens ?? 0} / ${ev.output_tokens ?? 0} = ${ev.total_tokens}` : "—"} />
        <Row label="成本" value={ev.cost_usd != null ? `$${ev.cost_usd.toFixed(4)}` : "—"} />
        <Row label="错误码" value={ev.error_code} />
        <Row label="错误消息" value={ev.error_message} />

        {/* Fallback 详情 */}
        {(ev.fallback_from || ev.fallback_to) && (
          <>
            <div style={{ marginTop: 8, marginBottom: 4, fontSize: 11, color: "var(--warning)", fontWeight: 600 }}>Fallback 详情</div>
            <Row label="从" value={ev.fallback_from} />
            <Row label="到" value={ev.fallback_to} />
            <Row label="原因" value={ev.fallback_reason} />
          </>
        )}

        {/* detail_json */}
        {ev.detail_json && (
          <>
            <div style={{ marginTop: 12, marginBottom: 4, fontSize: 11, color: "var(--muted)", fontWeight: 600 }}>完整详情</div>
            <pre style={{
              background: "var(--bg-base, #111)",
              border: "1px solid var(--line)",
              borderRadius: 4,
              padding: 8,
              fontSize: 11,
              lineHeight: 1.5,
              overflow: "auto",
              maxHeight: 300,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
              color: "var(--text-secondary)",
            }}>
              {typeof ev.detail_json === "string" ? ev.detail_json : JSON.stringify(ev.detail_json, null, 2)}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}
