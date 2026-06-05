import { useEffect, useState } from "react";
import { getObservabilitySummary, getObservabilityEvents, getObservabilityProviders, getRuntimeStats } from "../../api";
import type { ModelProvider } from "../../types";

/** S3: 模型可观测性面板 — 调用 /api/model-observability/* */
export default function ModelObservabilityPanel({ projectId }: { projectId?: number }) {
  const [summary, setSummary] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const [sRes, eRes, pRes] = await Promise.all([
          getObservabilitySummary(),
          getObservabilityEvents({ limit: 50 }),
          getObservabilityProviders(),
        ]);
        if (cancelled) return;
        setSummary(sRes);
        setEvents(Array.isArray(eRes) ? eRes : []);
        setProviders(Array.isArray(pRes) ? pRes : []);
      } catch (ex: any) {
        if (!cancelled) setErr(ex.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [projectId]);

  if (loading) return <div className="p-4 text-gray-400">加载中…</div>;
  if (err) return <div className="p-4 text-red-400">{err}</div>;

  const totalCalls = summary?.total_calls ?? 0;
  const successRate = summary?.success_rate != null ? (summary.success_rate * 100).toFixed(1) : "—";
  const avgLatency = summary?.avg_latency_ms != null ? `${Math.round(summary.avg_latency_ms)}ms` : "—";
  const totalTokens = summary?.total_tokens ?? 0;

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-100">模型可观测性</h2>

      {/* ── 概览卡片 ─────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[["总调用", totalCalls], ["成功率", `${successRate}%`], ["平均延迟", avgLatency], ["总 Token", totalTokens.toLocaleString()]].map(([label, v]) => (
          <div key={label} className="rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-4">
            <div className="text-xs text-gray-400">{label}</div>
            <div className="mt-1 text-xl font-bold text-gray-100">{v}</div>
          </div>
        ))}
      </div>

      {/* ── Provider 统计 ─────────────────────────── */}
      <div className="rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-300">Provider 统计</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400">
              <th className="py-1">Provider</th>
              <th className="py-1">调用</th>
              <th className="py-1">成功率</th>
              <th className="py-1">平均延迟</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p: any) => (
              <tr key={p.id} className="border-t border-[#2e2e2e]">
                <td className="py-2">{p.name}</td>
                <td className="py-2">{p.call_count ?? "—"}</td>
                <td className="py-2">{p.success_rate != null ? `${(p.success_rate * 100).toFixed(0)}%` : "—"}</td>
                <td className="py-2">{p.avg_latency_ms != null ? `${Math.round(p.avg_latency_ms)}ms` : "—"}</td>
              </tr>
            ))}
            {providers.length === 0 && (
              <tr><td colSpan={4} className="py-4 text-center text-gray-500">暂无数据</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── 最近事件 ─────────────────────────────── */}
      <div className="rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-300">最近事件</h3>
        <ul className="space-y-1 text-sm">
          {events.slice(0, 20).map((ev: any, i: number) => (
            <li key={i} className="flex gap-2 text-gray-300">
              <span className="shrink-0 text-xs text-gray-500">{new Date(ev.created_at).toLocaleTimeString()}</span>
              <span className="text-blue-400">{ev.event_type}</span>
              <span className="truncate">{ev.action}</span>
            </li>
          ))}
          {events.length === 0 && (
            <li className="py-4 text-center text-gray-500">暂无事件</li>
          )}
        </ul>
      </div>
    </div>
  );
}
