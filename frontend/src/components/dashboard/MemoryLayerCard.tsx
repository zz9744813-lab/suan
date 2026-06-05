import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAgentMemoryStats } from "../../api";
import { useProjectStore } from "../../stores/projectStore";

type LayerCounts = {
  temporary: number;
  task: number;
  long_term: number;
  permanent: number;
};

const LAYER_CONFIG: { key: keyof LayerCounts; label: string; color: string }[] = [
  { key: "temporary", label: "临时记忆", color: "var(--muted, #888)" },
  { key: "task", label: "任务记忆", color: "var(--primary, #4a90d9)" },
  { key: "long_term", label: "长时记忆", color: "var(--warning, #d4a85a)" },
  { key: "permanent", label: "永久记忆", color: "var(--state-ok, #4caf50)" },
];

export function MemoryLayerCard() {
  const navigate = useNavigate();
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [counts, setCounts] = useState<LayerCounts>({ temporary: 0, task: 0, long_term: 0, permanent: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentProjectId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    getAgentMemoryStats(currentProjectId)
      .then((res: any) => {
        if (cancelled) return;
        const byLayer = res?.by_layer ?? {};
        setCounts({
          temporary: byLayer.temporary ?? 0,
          task: byLayer.task ?? 0,
          long_term: byLayer.long_term ?? 0,
          permanent: byLayer.permanent ?? 0,
        });
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [currentProjectId]);

  const total = counts.temporary + counts.task + counts.long_term + counts.permanent;

  return (
    <div
      style={{
        padding: 12,
        borderRadius: 8,
        background: "var(--card)",
        border: "1px solid var(--line)",
        cursor: "pointer",
      }}
      onClick={() => navigate("/memory")}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>记忆分层</span>
        <span className="muted small">共 {total} 条</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {LAYER_CONFIG.map((layer) => (
          <span
            key={layer.key}
            className="pill"
            style={{ borderColor: layer.color, color: layer.color, fontSize: 11 }}
          >
            {layer.label}: {loading ? "…" : counts[layer.key]}
          </span>
        ))}
      </div>
    </div>
  );
}
