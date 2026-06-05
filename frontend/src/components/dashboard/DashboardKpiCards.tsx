import { useEffect, useState } from "react";
import { listTasks, getObservabilitySummary, listProjectMemoryEntities } from "../../api";
import { useProjectStore } from "../../stores/projectStore";

type Props = {
  projectId?: number | null;
};

type KpiData = {
  todayWords: number;
  todayChapters: number;
  qualityScore: number | null;
  apiHealth: number | null;
  todayCost: number | null;
};

export function DashboardKpiCards({ projectId }: Props) {
  const [data, setData] = useState<KpiData>({
    todayWords: 0,
    todayChapters: 0,
    qualityScore: null,
    apiHealth: null,
    todayCost: null,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);

        // 今日产出 — 完成 tasks
        const tasks = await listTasks({ status: "completed", limit: 100 }).catch(() => []);
        const arr = Array.isArray(tasks) ? tasks : [];
        const todayStr = new Date().toISOString().slice(0, 10);
        const todayTasks = arr.filter((t: any) =>
          t.completed_at?.startsWith(todayStr) || t.updated_at?.startsWith(todayStr),
        );
        const todayWords = todayTasks.reduce((sum: number, t: any) => sum + (t.word_count ?? t.output_word_count ?? 0), 0);

        // API 健康 + 成本
        let apiHealth: number | null = null;
        let todayCost: number | null = null;
        try {
          const summary = await getObservabilitySummary();
          apiHealth = summary?.success_rate != null ? summary.success_rate : null;
          todayCost = summary?.cost_usd != null ? summary.cost_usd : null;
        } catch {}

        // 质量分 — 从 review comments 聚合（简化：读最近的 memory entries）
        let qualityScore: number | null = null;
        if (projectId) {
          try {
            const memRes = await listProjectMemoryEntities(projectId, { limit: 10 });
            // 从 memory 中提取评分，如有
            const items = Array.isArray(memRes) ? memRes : (memRes as any)?.items ?? [];
            const scores = items
              .map((e: any) => e.confidence ?? e.quality_score)
              .filter((s: any): s is number => typeof s === "number" && s > 0);
            if (scores.length) qualityScore = scores.reduce((a: number, b: number) => a + b, 0) / scores.length;
          } catch {}
        }

        if (!cancelled) {
          setData({ todayWords, todayChapters: todayTasks.length, qualityScore, apiHealth, todayCost });
        }
      } catch {
        // silent
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const id = window.setInterval(load, 30000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [projectId]);

  function healthColor(rate: number | null): string {
    if (rate == null) return "var(--muted)";
    if (rate >= 0.95) return "var(--state-ok, #4caf50)";
    if (rate >= 0.8) return "var(--warning, #d4a85a)";
    return "var(--danger, #e05555)";
  }

  function costColor(cost: number | null): string {
    if (cost == null) return "var(--muted)";
    if (cost > 5) return "var(--danger, #e05555)";
    if (cost > 1) return "var(--warning, #d4a85a)";
    return "var(--state-ok, #4caf50)";
  }

  const cards = [
    {
      label: "今日产出",
      value: loading ? "…" : `${data.todayWords.toLocaleString()} 字 / ${data.todayChapters} 章`,
      color: undefined,
    },
    {
      label: "当前质量分",
      value: loading ? "…" : data.qualityScore != null ? `${(data.qualityScore * 100).toFixed(0)}%` : "—",
      color: data.qualityScore != null ? healthColor(data.qualityScore) : undefined,
    },
    {
      label: "API 健康",
      value: loading ? "…" : data.apiHealth != null ? `${(data.apiHealth * 100).toFixed(1)}%` : "—",
      color: healthColor(data.apiHealth),
    },
    {
      label: "今日成本",
      value: loading ? "…" : data.todayCost != null ? `$${data.todayCost.toFixed(2)}` : "—",
      color: costColor(data.todayCost),
    },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
      {cards.map((c) => (
        <div
          key={c.label}
          style={{
            padding: 12,
            borderRadius: 8,
            background: "var(--card)",
            border: "1px solid var(--line)",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.label}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: c.color ?? "var(--text)" }}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}
