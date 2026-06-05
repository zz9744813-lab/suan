/**
 * ReviewAutoFlowPanel — 自动评审流水线状态组件 (NF2 阶段4)
 *
 * 调用 /api/reviews/projects/{project_id}/auto-flow
 * 显示流水线步骤: chapter_completed → reader_review → triage → discussion → rewrite → done
 * 每步显示状态: done/running/queued/failed/waiting
 * 使用彩色圆点表示状态
 */
import { useEffect, useState } from "react";
import { getAutoFlowStatus } from "../../api";

type StepStatus = "done" | "running" | "queued" | "failed" | "waiting";

interface FlowStep {
  key: string;
  label: string;
  status: StepStatus;
  detail?: string;
}

const DEFAULT_STEPS: { key: string; label: string }[] = [
  { key: "chapter_completed", label: "章节完成" },
  { key: "reader_review", label: "读者评审" },
  { key: "triage", label: "分流/分组" },
  { key: "discussion", label: "讨论" },
  { key: "rewrite", label: "返工" },
  { key: "done", label: "完成" },
];

const STATUS_COLORS: Record<StepStatus, string> = {
  done: "#4caf50",
  running: "#2196f3",
  queued: "#ff9800",
  failed: "#f44336",
  waiting: "#bdbdbd",
};

const STATUS_LABELS: Record<StepStatus, string> = {
  done: "完成",
  running: "运行中",
  queued: "排队中",
  failed: "失败",
  waiting: "等待",
};

function normalizeSteps(raw: any): FlowStep[] {
  if (!raw || !raw.steps) return DEFAULT_STEPS.map((s) => ({ ...s, status: "waiting" as StepStatus }));
  const rawSteps = Array.isArray(raw.steps) ? raw.steps : [];
  const stepMap = new Map(rawSteps.map((s: any) => [s.key ?? s.step, s]));
  return DEFAULT_STEPS.map((def) => {
    const r = stepMap.get(def.key) as { status?: string; detail?: string; message?: string } | undefined;
    return {
      key: def.key,
      label: def.label,
      status: (r?.status ?? "waiting") as StepStatus,
      detail: r?.detail ?? r?.message,
    };
  });
}

export function ReviewAutoFlowPanel({ projectId, chapterId }: { projectId: number; chapterId?: number }) {
  const [steps, setSteps] = useState<FlowStep[]>(DEFAULT_STEPS.map((s) => ({ ...s, status: "waiting" as StepStatus })));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getAutoFlowStatus(projectId, chapterId)
      .then((r) => {
        if (mounted) setSteps(normalizeSteps(r));
      })
      .catch(() => {})
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [projectId, chapterId]);

  if (loading) return <div className="muted" style={{ fontSize: 12, padding: 8 }}>加载流水线…</div>;

  return (
    <div style={{ padding: 12, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>评审流水线</div>
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        {steps.map((step, i) => (
          <div key={step.key} style={{ display: "flex", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 72 }}>
              <div
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  background: STATUS_COLORS[step.status],
                  boxShadow: step.status === "running" ? `0 0 6px ${STATUS_COLORS[step.status]}` : "none",
                  transition: "background 0.3s",
                }}
                title={`${step.label}: ${STATUS_LABELS[step.status]}`}
              />
              <div style={{ fontSize: 11, marginTop: 4, textAlign: "center", fontWeight: step.status === "running" ? 600 : 400 }}>
                {step.label}
              </div>
              <div style={{ fontSize: 10, color: STATUS_COLORS[step.status] }}>
                {STATUS_LABELS[step.status]}
              </div>
              {step.detail && (
                <div className="muted" style={{ fontSize: 10, maxWidth: 80, textAlign: "center", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {step.detail}
                </div>
              )}
            </div>
            {i < steps.length - 1 && (
              <div
                style={{
                  width: 32,
                  height: 2,
                  background: steps[i + 1].status !== "waiting" ? "#90caf9" : "var(--border, #ddd)",
                  margin: "0 2px",
                  alignSelf: "flex-start",
                  marginTop: 7,
                }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
