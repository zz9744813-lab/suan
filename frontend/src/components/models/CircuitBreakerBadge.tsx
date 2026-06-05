/**
 * CircuitBreakerBadge — 熔断器状态徽标
 *
 * circuit_state: closed(绿) / half_open(黄) / open(红)
 * 显示 circuit_open_until
 */

const STATE_CONFIG: Record<string, { color: string; label: string }> = {
  closed: { color: "#4ade80", label: "正常" },
  half_open: { color: "#facc15", label: "半开" },
  open: { color: "#f87171", label: "熔断" },
};

interface Props {
  state: string;
  openUntil?: string | null;
}

export function CircuitBreakerBadge({ state, openUntil }: Props) {
  const cfg = STATE_CONFIG[state] ?? { color: "#999", label: state ?? "未知" };

  return (
    <span
      className="pill tiny"
      style={{
        background: cfg.color + "22",
        color: cfg.color,
        borderColor: cfg.color + "44",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.color, display: "inline-block" }} />
      熔断: {cfg.label}
      {state === "open" && openUntil && (
        <span className="muted" style={{ fontSize: 10, marginLeft: 2 }}>
          至 {new Date(openUntil).toLocaleTimeString("zh-CN")}
        </span>
      )}
    </span>
  );
}
