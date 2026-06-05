import { useEffect, useState } from "react";
import { getAgentRoleMatrix, listCurrentAgentRuns } from "../../api";

type AgentNode = {
  key: string;
  display_name: string;
  provider_name: string | null;
  model_name: string | null;
  status: "done" | "running" | "waiting" | "failed";
};

const PIPELINE_ORDER = [
  "planner", "drafter", "critic",
  "reader_hook", "reader_emotion", "reader_logic", "reader_commercial", "reader_toxic",
  "discussion",
  "rewriter", "continuity",
  "learner", "study",
  "memory_update",
];

const PIPELINE_LABELS: Record<string, string> = {
  planner: "Planner",
  drafter: "Draft",
  critic: "Critic",
  reader_hook: "Hook",
  reader_emotion: "Emotion",
  reader_logic: "Logic",
  reader_commercial: "Commercial",
  reader_toxic: "Toxic",
  discussion: "Discussion",
  rewriter: "Rewrite",
  continuity: "Continuity",
  learner: "Learner",
  study: "Study",
  memory_update: "Memory",
};

function statusColor(s: AgentNode["status"]): string {
  switch (s) {
    case "done": return "var(--state-ok, #4caf50)";
    case "running": return "var(--primary, #4a90d9)";
    case "waiting": return "var(--muted, #888)";
    case "failed": return "var(--danger, #e05555)";
  }
}

export function AgentPipelineVisualization() {
  const [nodes, setNodes] = useState<AgentNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const [matrixRes, runsRes] = await Promise.all([
          getAgentRoleMatrix().catch(() => null),
          listCurrentAgentRuns().catch(() => []),
        ]);

        const items = (matrixRes as any)?.items ?? [];
        const runs = Array.isArray(runsRes) ? runsRes : [];

        // 构建 Agent 状态 map
        const runMap = new Map<string, string>();
        runs.forEach((r: any) => {
          const key = r.agent_role_key ?? r.role_key;
          if (key) runMap.set(key, r.status ?? "running");
        });

        // 构建节点列表
        const nodeMap = new Map<string, AgentNode>();
        items.forEach((it: any) => {
          const key = it.role?.key;
          if (!key) return;
          nodeMap.set(key, {
            key,
            display_name: it.role?.display_name ?? key,
            provider_name: it.provider_name ?? it.binding?.provider_name ?? null,
            model_name: it.model_name ?? it.binding?.model_name ?? null,
            status: runMap.has(key) ? "running" : "waiting",
          });
        });

        // 按 PIPELINE_ORDER 排序，补充未出现的节点
        const ordered: AgentNode[] = PIPELINE_ORDER.map((key) => {
          const existing = nodeMap.get(key);
          if (existing) {
            // 从 runMap 获取状态
            const runStatus = runMap.get(key);
            if (runStatus === "completed" || runStatus === "done") {
              return { ...existing, status: "done" };
            }
            if (runStatus === "failed") {
              return { ...existing, status: "failed" };
            }
            if (runStatus === "running") {
              return { ...existing, status: "running" };
            }
            return existing;
          }
          return {
            key,
            display_name: PIPELINE_LABELS[key] ?? key,
            provider_name: null,
            model_name: null,
            status: "waiting" as const,
          };
        });

        // 添加不在预设列表中的节点
        items.forEach((it: any) => {
          const key = it.role?.key;
          if (key && !PIPELINE_ORDER.includes(key)) {
            ordered.push({
              key,
              display_name: it.role?.display_name ?? key,
              provider_name: it.provider_name ?? null,
              model_name: it.model_name ?? null,
              status: runMap.has(key) ? "running" : "waiting",
            });
          }
        });

        if (!cancelled) setNodes(ordered);
      } catch {
        // silent
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const id = window.setInterval(load, 10000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, []);

  if (loading && !nodes.length) {
    return <div className="muted small" style={{ padding: 12 }}>加载流水线…</div>;
  }

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 0,
      overflowX: "auto",
      padding: "8px 0",
    }}>
      {nodes.map((node, i) => (
        <div key={node.key} style={{ display: "flex", alignItems: "center" }}>
          {/* 节点 */}
          <div style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: `1px solid ${statusColor(node.status)}`,
            background: node.status === "running"
              ? "rgba(74, 144, 217, 0.1)"
              : "var(--card)",
            minWidth: 60,
            textAlign: "center",
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: statusColor(node.status) }}>
              {node.display_name}
            </div>
            {node.model_name && (
              <div style={{ fontSize: 9, color: "var(--muted)", marginTop: 2, whiteSpace: "nowrap" }}>
                {node.provider_name}/{node.model_name.length > 16 ? node.model_name.slice(0, 14) + "…" : node.model_name}
              </div>
            )}
          </div>

          {/* 箭头 */}
          {i < nodes.length - 1 && (
            <div style={{ color: "var(--muted)", fontSize: 14, padding: "0 2px", flexShrink: 0 }}>→</div>
          )}
        </div>
      ))}
    </div>
  );
}
