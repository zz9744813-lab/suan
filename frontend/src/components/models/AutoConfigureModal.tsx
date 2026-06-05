/**
 * AutoConfigureModal — 新 Provider 创建后一键为所有写作 Agent 绑定真实模型
 *
 * 显示推荐绑定列表, 支持一键确认或手动跳过。
 */
import { useState } from "react";
import type { AgentRoleMatrixItem, ModelProvider } from "../../types";
import { updateAgentModelBinding } from "../../api";

type AgentBindingTask = {
  agentRoleId: number;
  agentKey: string;
  agentDisplayName: string;
  modelName: string;
  reason: string;
};

function planBindings(
  matrixItems: AgentRoleMatrixItem[],
  provider: ModelProvider,
): AgentBindingTask[] {
  const primaryModel = provider.default_model || "claude-3.5-sonnet";
  const cheapModel = "gemini-flash-1.5";
  const tasks: AgentBindingTask[] = [];

  for (const item of matrixItems) {
    const key = item.role.key.toLowerCase();
    const name = item.role.display_name;

    if (key.startsWith("reader")) {
      tasks.push({
        agentRoleId: item.role.id,
        agentKey: item.role.key,
        agentDisplayName: name,
        modelName: cheapModel,
        reason: "速度快,成本低",
      });
    } else if (key === "planner" || key === "drafter" || key === "critic") {
      let reason: string;
      if (key === "planner") reason = "规划能力强";
      else if (key === "drafter") reason = "写作质量高";
      else reason = "评审严格";
      tasks.push({
        agentRoleId: item.role.id,
        agentKey: item.role.key,
        agentDisplayName: name,
        modelName: primaryModel,
        reason,
      });
    }
  }

  return tasks;
}

export type AutoConfigureModalProps = {
  open: boolean;
  provider: ModelProvider | null;
  matrixItems: AgentRoleMatrixItem[];
  onClose: () => void;
  onConfigured: () => void;
};

export function AutoConfigureModal({
  open,
  provider,
  matrixItems,
  onClose,
  onConfigured,
}: AutoConfigureModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [agentStatus, setAgentStatus] = useState<Record<number, string>>({});

  if (!open || !provider) return null;

  const bindings = planBindings(matrixItems, provider);

  const handleAutoConfigure = async () => {
    setSubmitting(true);
    const status: Record<number, string> = {};
    for (const task of bindings) {
      try {
        await updateAgentModelBinding(task.agentRoleId, {
          provider_id: provider.id,
          model_name: task.modelName,
          selection_mode: "manual",
        });
        status[task.agentRoleId] = "ok";
      } catch (e: any) {
        status[task.agentRoleId] = String(e?.message ?? "失败");
      }
      setAgentStatus({ ...status });
    }
    setSubmitting(false);
    onConfigured();
  };

  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        className="modal-panel"
        style={{
          background: "var(--bg-primary)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "24px 28px",
          minWidth: 480,
          maxWidth: 560,
          boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
        }}
      >
        <h3 style={{ margin: "0 0 6px", fontSize: 16, color: "var(--text-primary)" }}>
          {provider.name} 已就绪
        </h3>
        <p style={{ margin: "0 0 18px", fontSize: 13, color: "var(--text-muted)" }}>
          一键为所有写作 Agent 绑定真实模型
        </p>

        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 18 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "4px 8px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>Agent</th>
              <th style={{ textAlign: "left", padding: "4px 8px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>模型</th>
              <th style={{ textAlign: "left", padding: "4px 8px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500 }}>说明</th>
              <th style={{ textAlign: "center", padding: "4px 8px", fontSize: 12, color: "var(--text-muted)", fontWeight: 500, width: 48 }}>状态</th>
            </tr>
          </thead>
          <tbody>
            {bindings.map((task) => {
              const st = agentStatus[task.agentRoleId];
              return (
                <tr key={task.agentRoleId} style={{ borderBottom: "1px solid var(--border-secondary)" }}>
                  <td style={{ padding: "6px 8px", fontSize: 13, color: "var(--text-primary)" }}>{task.agentDisplayName}</td>
                  <td style={{ padding: "6px 8px", fontSize: 13, fontFamily: "monospace", color: "var(--text-secondary)" }}>{task.modelName}</td>
                  <td style={{ padding: "6px 8px", fontSize: 12, color: "var(--text-muted)" }}>{task.reason}</td>
                  <td style={{ padding: "6px 8px", textAlign: "center" }}>
                    {st === "ok" ? (
                      <span style={{ color: "#5d9c5d", fontSize: 14 }}>&#10003;</span>
                    ) : st ? (
                      <span style={{ color: "#c45858", fontSize: 11 }} title={st}>失败</span>
                    ) : (
                      <span style={{ color: "var(--text-muted)", fontSize: 11 }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            className="input"
            style={{
              padding: "6px 16px",
              cursor: "pointer",
              background: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--text-secondary)",
            }}
            onClick={onClose}
            disabled={submitting}
          >
            手动调整
          </button>
          <button
            className="primary"
            style={{
              padding: "6px 16px",
              cursor: submitting ? "not-allowed" : "pointer",
              opacity: submitting ? 0.7 : 1,
              border: "none",
              borderRadius: 4,
              fontWeight: 500,
            }}
            onClick={handleAutoConfigure}
            disabled={submitting}
          >
            {submitting ? "绑定中..." : "使用推荐配置"}
          </button>
        </div>
      </div>
    </div>
  );
}
