import { useRef, useCallback } from "react";

type Props = {
  events: any[];
  loading: boolean;
  onLoadMore: () => void;
  hasMore: boolean;
  onClickEvent: (eventId: number) => void;
};

function eventStatus(ev: any): { label: string; color: string; borderColor: string } {
  if (ev.status === "failed" || ev.event_type === "failed") {
    return { label: "失败", color: "var(--danger, #e05555)", borderColor: "3px solid var(--danger, #e05555)" };
  }
  if (ev.is_fallback || ev.event_type === "fallback") {
    return { label: "Fallback", color: "var(--warning, #d4a85a)", borderColor: "3px solid var(--warning, #d4a85a)" };
  }
  if (ev.status === "running" || ev.event_type === "running") {
    return { label: "运行中", color: "var(--primary, #4a90d9)", borderColor: "3px solid var(--primary, #4a90d9)" };
  }
  return { label: "成功", color: "var(--state-ok, #4caf50)", borderColor: "none" };
}

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false }); }
  catch { return iso; }
}

export function ObservabilityEventStream({ events, loading, onLoadMore, hasMore, onClickEvent }: Props) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  const observerCallback = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      if (entries[0]?.isIntersecting && hasMore) onLoadMore();
    },
    [hasMore, onLoadMore],
  );

  // 简易无限滚动
  const lastRef = (el: HTMLDivElement | null) => {
    if (!el) return;
    const obs = new IntersectionObserver(observerCallback, { rootMargin: "200px" });
    obs.observe(el);
    // 清理由 observer 自行处理
  };

  if (loading && !events.length) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!events.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无事件</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 400, overflowY: "auto" }}>
      {events.map((ev: any, i: number) => {
        const st = eventStatus(ev);
        const isFailed = st.label === "失败";
        const isFallback = st.label === "Fallback";
        const isRunning = st.label === "运行中";
        const borderLeft = (isFailed || isFallback || isRunning) ? st.borderColor : "none";

        return (
          <div
            key={ev.id ?? i}
            ref={i === events.length - 1 ? lastRef : undefined}
            style={{
              padding: "8px 12px",
              borderRadius: 6,
              background: "var(--card)",
              border: "1px solid var(--line)",
              borderLeft,
              cursor: "pointer",
            }}
            onClick={() => ev.id != null && onClickEvent(ev.id)}
          >
            {/* 第一行：时间 + Agent + Provider/Model + 状态标签 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12 }}>
                <span style={{ color: "var(--muted)", marginRight: 8 }}>{formatTime(ev.created_at)}</span>
                <span style={{ fontWeight: 600, marginRight: 6 }}>{ev.agent_role_key ?? ev.agent_name ?? "—"}</span>
                <span style={{ color: "var(--muted)", fontSize: 11 }}>
                  {ev.provider_name ?? "—"}/{ev.model_name ?? "—"}
                </span>
              </span>
              <span className="pill" style={{ fontSize: 10, color: st.color, borderColor: st.color }}>
                {st.label}
              </span>
            </div>

            {/* 第二行：摘要 */}
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
              {ev.event_type === "failed" || ev.status === "failed"
                ? (ev.error_type ?? ev.failure_type ?? "请求失败")
                : "请求成功"}
              {ev.latency_ms != null ? ` · ${Math.round(ev.latency_ms)}ms` : ""}
              {ev.total_tokens != null ? ` · ${ev.total_tokens} tokens` : ""}
              {ev.cost_usd != null ? ` · $${ev.cost_usd.toFixed(4)}` : ""}
            </div>

            {/* 第三行：项目/章节/task */}
            {(ev.project_name || ev.chapter_id || ev.task_id) && (
              <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                {ev.project_name && `项目 ${ev.project_name}`}
                {ev.chapter_id && ` · 第${ev.chapter_id}章`}
                {ev.task_id && ` · task #${ev.task_id}`}
              </div>
            )}

            {/* 第四行：失败时显示错误 */}
            {isFailed && ev.error_message && (
              <div style={{ fontSize: 11, color: "var(--danger, #e05555)", marginTop: 2 }}>
                错误：{ev.error_message}
              </div>
            )}

            {/* Fallback 详情 */}
            {isFallback && ev.fallback_from && (
              <div style={{ fontSize: 11, color: "var(--warning, #d4a85a)", marginTop: 2 }}>
                fallback 已触发
              </div>
            )}
          </div>
        );
      })}

      {loading && <div className="muted small" style={{ padding: 8, textAlign: "center" }}>加载更多…</div>}
      {!hasMore && events.length > 0 && (
        <div className="muted small" style={{ padding: 8, textAlign: "center" }}>已全部加载</div>
      )}
    </div>
  );
}
