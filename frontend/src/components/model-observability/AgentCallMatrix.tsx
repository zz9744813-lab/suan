type Props = {
  agents: any[];
  loading: boolean;
  onClickAgent: (agentRoleKey: string) => void;
};

const AGENT_SECTIONS: { title: string; keys: string[] }[] = [
  { title: "写作 Agent", keys: ["planner", "drafter", "critic", "rewriter", "continuity"] },
  { title: "读者 Agent", keys: ["reader_hook", "reader_emotion", "reader_logic", "reader_commercial", "reader_toxic"] },
  { title: "主 Agent", keys: ["chief_comment_moderator", "discussion"] },
  { title: "记忆 Agent", keys: ["memory_update"] },
  { title: "拆书 Agent", keys: ["learner", "study"] },
];

function statusLabel(status: string): { text: string; color: string } {
  switch (status) {
    case "healthy": case "done": return { text: "正常", color: "var(--state-ok, #4caf50)" };
    case "running": return { text: "运行中", color: "var(--primary, #4a90d9)" };
    case "degraded": case "slow": return { text: "降级", color: "var(--warning, #d4a85a)" };
    case "failed": case "down": return { text: "异常", color: "var(--danger, #e05555)" };
    default: return { text: "未知", color: "var(--muted, #888)" };
  }
}

export function AgentCallMatrix({ agents, loading, onClickAgent }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  // 按 section 分组
  const agentMap = new Map<string, any>();
  agents.forEach((a: any) => agentMap.set(a.agent_role_key ?? a.key, a));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {AGENT_SECTIONS.map((section) => {
        const sectionAgents = section.keys
          .map((k) => agentMap.get(k))
          .filter(Boolean);

        // 也显示不在预设 section 中的 agent（追加到末尾）
        // 主循环中只显示已匹配的
        if (sectionAgents.length === 0) return null;

        return (
          <div key={section.title}>
            <div className="muted small" style={{ marginBottom: 8, letterSpacing: 1 }}>
              {section.title}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
              {sectionAgents.map((a: any) => {
                const key = a.agent_role_key ?? a.key;
                const st = statusLabel(a.health_status ?? "unknown");
                const sr = a.success_rate ?? 0;

                return (
                  <div
                    key={key}
                    style={{
                      padding: 12,
                      borderRadius: 8,
                      border: "1px solid var(--line)",
                      cursor: "pointer",
                      transition: "box-shadow 0.15s",
                    }}
                    onClick={() => onClickAgent(key)}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = "0 2px 8px rgba(0,0,0,0.15)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = "none"; }}
                  >
                    {/* 第一行：Agent 名 + 状态 */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>{a.display_name ?? a.agent_name ?? key}</span>
                      <span style={{ fontSize: 11, color: st.color }}>
                        <span style={{
                          display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                          background: st.color, marginRight: 4, verticalAlign: "middle",
                        }} />
                        {st.text}
                      </span>
                    </div>
                    {/* 第二行：Provider / Model */}
                    <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 2 }}>
                      {a.provider_name ?? "—"} / {a.model_name ?? "—"}
                    </div>
                    {/* 第三行：绑定模式 / 类别 */}
                    <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                      {[a.selection_mode, a.category].filter(Boolean).join(" · ")}
                    </div>
                    {/* 第四行：今日统计 */}
                    <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      今日 {a.call_count ?? 0} 次 · {(sr * 100).toFixed(0)}% · {a.avg_latency_ms != null ? `${Math.round(a.avg_latency_ms / 100) / 10}s` : "—"} · ${a.cost_usd != null ? a.cost_usd.toFixed(2) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* 未在预设 section 中的 agent */}
      {(() => {
        const covered = new Set(AGENT_SECTIONS.flatMap((s) => s.keys));
        const rest = agents.filter((a: any) => !covered.has(a.agent_role_key ?? a.key));
        if (!rest.length) return null;
        return (
          <div>
            <div className="muted small" style={{ marginBottom: 8, letterSpacing: 1 }}>其他 Agent</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
              {rest.map((a: any) => {
                const key = a.agent_role_key ?? a.key;
                const st = statusLabel(a.health_status ?? "unknown");
                const sr = a.success_rate ?? 0;
                return (
                  <div
                    key={key}
                    style={{ padding: 12, borderRadius: 8, border: "1px solid var(--line)", cursor: "pointer" }}
                    onClick={() => onClickAgent(key)}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: 13 }}>{a.display_name ?? key}</span>
                      <span style={{ fontSize: 11, color: st.color }}>{st.text}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                      {a.provider_name ?? "—"} / {a.model_name ?? "—"}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {a.call_count ?? 0} 次 · {(sr * 100).toFixed(0)}% · ${a.cost_usd != null ? a.cost_usd.toFixed(2) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
