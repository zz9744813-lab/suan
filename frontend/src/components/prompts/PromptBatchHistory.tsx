/**
 * PromptBatchHistory — 填充批次历史列表 (NF2 阶段1)
 *
 * 显示最近的 auto-fill 批次
 * 每行: batch_key, 状态, 时间, 应用数量
 * 支持回滚
 */
export function PromptBatchHistory({
  batches,
  onRollback,
}: {
  batches: any[];
  onRollback: (batchKey: string) => void;
}) {
  if (batches.length === 0) {
    return <div className="muted" style={{ fontSize: 12, padding: 8 }}>暂无填充记录</div>;
  }

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>填充历史</div>
      {batches.map((b, i) => (
        <div
          key={b.batch_key ?? i}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 0",
            borderBottom: "1px solid var(--border, #eee)",
          }}
        >
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, flex: 1 }}>
            {b.batch_key}
          </span>
          <span
            className="pill"
            style={{
              fontSize: 10,
              background: b.status === "applied" ? "#e8f5e9" : b.status === "rolled_back" ? "#fce4ec" : "#fff3e0",
              color: b.status === "applied" ? "#2e7d32" : b.status === "rolled_back" ? "#c62828" : "#e65100",
            }}
          >
            {b.status}
          </span>
          <span className="muted" style={{ fontSize: 11, minWidth: 80 }}>
            {b.created_at ? new Date(b.created_at).toLocaleString("zh-CN") : ""}
          </span>
          <span className="muted" style={{ fontSize: 11, minWidth: 36 }}>
            {b.applied_count ?? 0} 项
          </span>
          {b.status === "applied" && (
            <button
              className="tiny"
              style={{ color: "#c62828" }}
              onClick={() => onRollback(b.batch_key)}
            >
              回滚
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
