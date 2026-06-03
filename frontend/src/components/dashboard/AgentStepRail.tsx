/**
 * AgentStepRail — Round 3 (P1-UI-5) + (P1-FUNC-1).
 *
 * Visualises one task's pipeline as an 8-stop track. Each stop is
 * a small badge with a glyph + status. Drives off the backend
 * ``TaskDiagnosis.steps`` so the rail matches what the diagnosis
 * actually says (which itself accounts for the fact that failed
 * tasks often have no AgentStep rows on disk).
 *
 * Layout: a horizontal flex row of stops separated by connectors.
 * On narrow screens it wraps; the connector line is a thin gold
 * bar that gets recoloured to red when a stop failed.
 */
import type { TaskDiagnosisStep } from "../../types";
import "./AgentStepRail.css";

type Props = {
  steps: TaskDiagnosisStep[];
  compact?: boolean;
  onStepClick?: (step: TaskDiagnosisStep) => void;
};

const GLYPHS: Record<string, string> = {
  context_compile: "≣",
  plan: "✦",
  draft: "✎",
  review: "◎",
  rewrite: "↻",
  continuity: "⇄",
  memory_update: "❒",
  learning: "✧",
};

export function AgentStepRail({ steps, compact, onStepClick }: Props) {
  return (
    <ol className={`agent-rail ${compact ? "agent-rail-compact" : ""}`}>
      {steps.map((s, idx) => (
        <li
          key={s.step_name + idx}
          className={`agent-rail-step status-${s.status} ${onStepClick ? "clickable" : ""}`}
          onClick={onStepClick ? () => onStepClick(s) : undefined}
          title={[
            s.label,
            s.agent_name ? `(${s.agent_name})` : "",
            s.score != null ? `分数 ${s.score}` : "",
            s.error_message ? `错误：${s.error_message.slice(0, 80)}` : "",
          ].filter(Boolean).join(" · ")}
        >
          <span className="agent-rail-dot">
            <span className="agent-rail-glyph">{GLYPHS[s.step_name] ?? "•"}</span>
          </span>
          <span className="agent-rail-text">
            <span className="agent-rail-label">{s.label}</span>
            <span className="agent-rail-meta">
              {s.status === "succeeded" && s.score != null ? `${s.score}分` : statusText(s.status)}
              {s.status === "succeeded" && s.cost_usd > 0 ? ` · $${s.cost_usd.toFixed(3)}` : ""}
              {s.status === "failed" && s.error_message ? ` · 失败` : ""}
            </span>
          </span>
          {idx < steps.length - 1 && <span className="agent-rail-connector" />}
        </li>
      ))}
    </ol>
  );
}

function statusText(s: string): string {
  switch (s) {
    case "succeeded": return "通过";
    case "failed": return "失败";
    case "running": return "运行中";
    case "skipped": return "跳过";
    case "pending": return "等待";
    default: return s;
  }
}
