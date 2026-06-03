/**
 * FailureDiagnosisCard — Round 3 (P1-UI-7) + (P1-FUNC-1).
 *
 * Takes a failed / cancelled task, fetches its diagnosis, and
 * renders a readable, actionable card. The diagnosis endpoint
 * supplies:
 *   - failed_agent / failed_step (or inferred from error text)
 *   - impact (list of skipped steps)
 *   - typed suggestions (buttons that call real backend endpoints)
 *   - raw output / prompt previews
 *
 * Action surface:
 *   - 复制错误     : copy the original error text
 *   - 重跑任务     : POST /api/tasks/{id}/retry (full)
 *   - 只重跑失败   : POST /api/tasks/{id}/retry {mode: from_failed_step}
 *   - 使用 fallback: POST /api/tasks/{id}/retry {mode: continue_with_fallback}
 *   - 打开模型配置  : link to /models
 *   - 查看 Step    : link to the chapter detail
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getTaskDiagnosis, retryTask, type RetryMode,
} from "../../api";
import type { AgentTask, TaskDiagnosis, TaskDiagnosisSuggestion } from "../../types";
import "./FailureDiagnosisCard.css";

type Props = {
  task: AgentTask;
  onChanged: () => void;
};

export function FailureDiagnosisCard({ task, onChanged }: Props) {
  const [diag, setDiag] = useState<TaskDiagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await getTaskDiagnosis(task.id);
        if (!cancelled) setDiag(d);
      } catch { /* leave diag null */ }
    })();
    return () => { cancelled = true; };
  }, [task.id]);

  const errorText = diag?.error_message ?? task.error ?? "（未提供错误信息）";
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(errorText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const onSuggestion = async (s: TaskDiagnosisSuggestion) => {
    setBusy(true);
    try {
      if (s.type === "safe_retry") {
        await retryTask(task.id, { mode: "full" });
        onChanged();
      } else if (s.type === "from_failed_step") {
        // The diagnosis's params.task_id carries the task; we need
        // the step name. The frontend maps the rail's failed_step
        // to the retry's from_step.
        const fromStep = diag?.failed_step ?? undefined;
        await retryTask(task.id, { mode: "from_failed_step", from_step: fromStep });
        onChanged();
      } else if (s.type === "continue_with_fallback") {
        await retryTask(task.id, { mode: "continue_with_fallback" });
        onChanged();
      } else if (s.type === "switch_model") {
        // /models is the only safe landing — actual role binding
        // editing is a separate flow.
        window.location.href = "/models";
      }
      // "view_step" and "open_models" are <a> links, not buttons.
    } catch (e: any) {
      alert(`操作失败：${e?.message ?? String(e)}`);
    } finally { setBusy(false); }
  };

  return (
    <div className="failure-card">
      <div className="failure-headline">
        <span className="badge error">失败</span>
        <span className="failure-task-id">任务 #{task.id} · {task.task_type}</span>
        <span className="spacer" />
        <span className="badge tiny warn">{diag?.error_type ?? "诊断中…"}</span>
      </div>

      <div className="failure-grid">
        <Cell label="失败 Agent" value={diag?.failed_agent ?? "—"} />
        <Cell label="失败 Step" value={diag?.failed_step ?? "—"} />
        <Cell
          label="章节"
          value={
            task.chapter_id ? (
              <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`}>
                第 {task.chapter_id} 章
              </Link>
            ) : <span className="muted">—</span>
          }
        />
        <Cell label="已重试" value={`${task.retry_count ?? 0} 次`} />
      </div>

      {diag?.impact && diag.impact.length > 0 && (
        <div className="failure-section">
          <div className="failure-section-label">影响</div>
          <div className="failure-impact">
            {diag.impact.map((i, idx) => (
              <span key={idx} className="failure-impact-chip">{i}</span>
            ))}
          </div>
        </div>
      )}

      <div className="failure-section">
        <div className="failure-section-label">原始错误</div>
        <details open>
          <summary className="failure-summary muted small">点击展开 / 收起</summary>
          <pre className="failure-pre">{errorText}</pre>
        </details>
      </div>

      {diag?.raw_output_preview && (
        <div className="failure-section">
          <div className="failure-section-label">原始输出 preview（前 800 字）</div>
          <pre className="failure-pre faint">{diag.raw_output_preview}</pre>
        </div>
      )}

      {diag?.prompt_preview && (
        <div className="failure-section">
          <div className="failure-section-label">对应 Prompt preview（前 800 字）</div>
          <pre className="failure-pre faint">{diag.prompt_preview}</pre>
        </div>
      )}

      {diag && diag.suggestions.length > 0 && (
        <div className="failure-section">
          <div className="failure-section-label">建议操作</div>
          <div className="failure-suggestions">
            {diag.suggestions.map((s, idx) => (
              <SuggestionButton
                key={idx}
                suggestion={s}
                disabled={busy}
                onClick={() => onSuggestion(s)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="failure-actions">
        <button onClick={onCopy} disabled={busy}>
          {copied ? "已复制 ✓" : "复制错误"}
        </button>
        {task.chapter_id && (
          <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`} className="button">
            查看 Step
          </Link>
        )}
        <button onClick={() => onSuggestion({ type: "safe_retry", label: "重试", description: "", risk: "low", params: { task_id: task.id } })} disabled={busy}>
          重跑（完整）
        </button>
        <span className="spacer" />
        <Link to="/models" className="button">打开模型配置</Link>
      </div>
    </div>
  );
}

function Cell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="failure-cell">
      <div className="failure-cell-label muted tiny">{label}</div>
      <div className="failure-cell-value">{value}</div>
    </div>
  );
}

function SuggestionButton({
  suggestion, onClick, disabled,
}: {
  suggestion: TaskDiagnosisSuggestion;
  onClick: () => void;
  disabled: boolean;
}) {
  // "view_step" / "open_models" are link-only — render as <a>.
  if (suggestion.type === "view_step" && suggestion.params?.chapter_id) {
    return (
      <Link
        className="failure-suggestion-button"
        to={`/projects/${suggestion.params.project_id}/chapters/${suggestion.params.chapter_id}`}
      >
        <div className="fsg-label">
          {suggestion.label}
          <span className="fsg-risk">查看</span>
        </div>
        <div className="fsg-desc muted small">{suggestion.description}</div>
      </Link>
    );
  }
  if (suggestion.type === "open_models") {
    return (
      <Link className="failure-suggestion-button" to="/models">
        <div className="fsg-label">
          {suggestion.label}
          <span className="fsg-risk">配置</span>
        </div>
        <div className="fsg-desc muted small">{suggestion.description}</div>
      </Link>
    );
  }
  return (
    <button
      type="button"
      className="failure-suggestion-button"
      onClick={onClick}
      disabled={disabled}
    >
      <div className="fsg-label">
        {suggestion.label}
        <span className={`fsg-risk risk-${suggestion.risk}`}>风险 {suggestion.risk}</span>
      </div>
      <div className="fsg-desc muted small">{suggestion.description}</div>
    </button>
  );
}
