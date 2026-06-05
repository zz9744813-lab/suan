/**
 * AutoConfigureToolbar — 一键自动配置工具栏
 *
 * 按钮: "预览选择" / "一键自动配置"
 * 调用 previewModelSelection 和 autoConfigureAgents API
 */
import { useState } from "react";
import { previewModelSelection, autoConfigureAgents } from "../../api";
import type { PreviewSelectionResponse } from "../../api";

interface Props {
  roleId: number;
  agentRoleKey: string;
  onConfigured: () => void;
}

export function AutoConfigureToolbar({ roleId, agentRoleKey, onConfigured }: Props) {
  const [previewData, setPreviewData] = useState<PreviewSelectionResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [configuring, setConfiguring] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handlePreview() {
    setPreviewLoading(true);
    setMessage(null);
    try {
      const res = await previewModelSelection(roleId, { agent_role_key: agentRoleKey });
      setPreviewData(res);
    } catch (e: any) {
      setMessage(`预览失败: ${e?.message ?? e}`);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleAutoConfigure() {
    setConfiguring(true);
    setMessage(null);
    try {
      const res = await autoConfigureAgents({ scope: "auto_only" });
      setMessage(`已更新 ${res.updated} 个角色${res.skipped_manual > 0 ? `，跳过 ${res.skipped_manual} 个手动绑定` : ""}`);
      onConfigured();
    } catch (e: any) {
      setMessage(`配置失败: ${e?.message ?? e}`);
    } finally {
      setConfiguring(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
        <button className="tiny primary" onClick={handlePreview} disabled={previewLoading}>
          {previewLoading ? "预览中…" : "预览选择"}
        </button>
        <button className="tiny" onClick={handleAutoConfigure} disabled={configuring}>
          {configuring ? "配置中…" : "一键自动配置"}
        </button>
      </div>
      {message && (
        <div className="small" style={{ marginBottom: 6, color: message.includes("失败") ? "#f87171" : "#4ade80" }}>
          {message}
        </div>
      )}
      {previewData && (
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid #2e2e2e", borderRadius: 4, padding: 8, fontSize: 12 }}>
          <div>
            <span className="muted small">推荐</span> · {previewData.selected.provider_name ?? `#${previewData.selected.provider_id}`} / {previewData.selected.model_name}
            <span className="muted small" style={{ marginLeft: 8 }}>Score {previewData.selected.score.toFixed(2)}</span>
          </div>
          {previewData.candidates.length > 1 && (
            <details style={{ marginTop: 4 }}>
              <summary className="muted small" style={{ cursor: "pointer" }}>
                其他候选 ({previewData.candidates.length - 1})
              </summary>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, marginTop: 4 }}>
                {previewData.candidates.filter((c) => c !== previewData.selected).map((c) => (
                  <li key={`${c.provider_id}-${c.model_name}`} className="muted small">
                    {c.provider_name ?? `#${c.provider_id}`} / {c.model_name} ({c.score.toFixed(2)})
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
