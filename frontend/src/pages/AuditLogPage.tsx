import { useEffect, useState } from "react";
import { listAuditLogs } from "../api";

export function AuditLogPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await listAuditLogs({ limit: 100 });
        if (!cancelled) {
          const items = Array.isArray(res)
            ? res
            : Array.isArray(res?.data)
              ? res.data
              : res?.items ?? res?.data?.items ?? [];
          setLogs(items);
        }
      } catch (e: any) {
        if (!cancelled) setErr(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div className="p-6 text-gray-400">加载审计日志…</div>;
  if (err) return <div className="p-6 text-red-400">{err}</div>;

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold text-gray-100">审计日志</h1>
      <div className="rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b border-[#2e2e2e]">
              <th className="py-2 px-3">时间</th>
              <th className="py-2 px-3">事件</th>
              <th className="py-2 px-3">操作者</th>
              <th className="py-2 px-3">动作</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log: any) => (
              <tr key={log.id} className="border-b border-[#2e2e2e] text-gray-300">
                <td className="py-2 px-3 text-xs text-gray-500">
                  {new Date(log.created_at).toLocaleString()}
                </td>
                <td className="py-2 px-3">
                  <span className="px-1.5 py-0.5 rounded text-xs bg-blue-900/40 text-blue-300">
                    {log.event_type}
                  </span>
                </td>
                <td className="py-2 px-3 text-xs">{log.actor_key || log.actor_type}</td>
                <td className="py-2 px-3">{log.action}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={4} className="py-8 text-center text-gray-500">
                  暂无审计日志
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
