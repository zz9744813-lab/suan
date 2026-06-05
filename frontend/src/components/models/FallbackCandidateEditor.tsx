/**
 * FallbackCandidateEditor — Fallback 候选编辑器 (增强版)
 *
 * 支持:
 *   Provider 下拉 (只显示 enabled)
 *   Model 下拉/输入
 *   权重设置
 *   删除候选
 *   新增候选
 */
import { useState } from "react";
import type { ModelProvider } from "../../types";

interface FallbackCandidate {
  provider_id: number;
  model_name: string;
  weight?: number;
}

interface Props {
  candidates: FallbackCandidate[];
  onChange: (c: FallbackCandidate[]) => void;
  allowAutoFallback: boolean;
  onAllowChange: (v: boolean) => void;
  providers?: ModelProvider[];
}

export function FallbackCandidateEditor({
  candidates, onChange, allowAutoFallback, onAllowChange, providers,
}: Props) {
  const [draftProvider, setDraftProvider] = useState<number | null>(null);
  const [draftModel, setDraftModel] = useState("");

  const enabledProviders = (providers ?? []).filter((p) => p.enabled);

  function addCandidate() {
    const model = draftModel.trim();
    if (!draftProvider || !model) return;
    // 防止重复
    if (candidates.some((c) => c.provider_id === draftProvider && c.model_name === model)) return;
    onChange([...candidates, { provider_id: draftProvider, model_name: model, weight: 1 }]);
    setDraftProvider(null);
    setDraftModel("");
  }

  function removeCandidate(index: number) {
    onChange(candidates.filter((_, i) => i !== index));
  }

  function updateWeight(index: number, weight: number) {
    const updated = [...candidates];
    updated[index] = { ...updated[index], weight };
    onChange(updated);
  }

  function getProviderName(pid: number): string {
    if (enabledProviders.length > 0) {
      const p = enabledProviders.find((p) => p.id === pid);
      if (p) return p.name;
    }
    return `Provider #${pid}`;
  }

  return (
    <div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={allowAutoFallback}
          onChange={(e) => onAllowChange(e.target.checked)}
        />
        <span className="small">允许自动 Fallback</span>
      </label>

      {candidates.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 8, fontSize: 12 }}>
          <thead>
            <tr>
              <th className="muted small" style={{ textAlign: "left", padding: "2px 6px" }}>Provider</th>
              <th className="muted small" style={{ textAlign: "left", padding: "2px 6px" }}>Model</th>
              <th className="muted small" style={{ textAlign: "left", padding: "2px 6px", width: 60 }}>权重</th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c, i) => (
              <tr key={i}>
                <td style={{ padding: "2px 6px" }}>{getProviderName(c.provider_id)}</td>
                <td style={{ padding: "2px 6px" }}>{c.model_name}</td>
                <td style={{ padding: "2px 6px" }}>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={10}
                    step={0.5}
                    value={c.weight ?? 1}
                    onChange={(e) => updateWeight(i, Number(e.target.value))}
                    style={{ width: 48, fontSize: 11 }}
                  />
                </td>
                <td><button className="tiny" onClick={() => removeCandidate(i)} title="移除">✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* 新增候选 */}
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {enabledProviders.length > 0 ? (
          <select
            className="input"
            value={draftProvider ?? ""}
            onChange={(e) => setDraftProvider(e.target.value ? Number(e.target.value) : null)}
            style={{ width: 130 }}
          >
            <option value="">-- Provider --</option>
            {enabledProviders.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        ) : (
          <input
            className="input"
            placeholder="Provider ID"
            type="number"
            value={draftProvider ?? ""}
            onChange={(e) => setDraftProvider(e.target.value ? Number(e.target.value) : null)}
            style={{ width: 100 }}
          />
        )}
        <input
          className="input"
          placeholder="Model 名称"
          value={draftModel}
          onChange={(e) => setDraftModel(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addCandidate(); }}
          style={{ flex: 1 }}
        />
        <button
          className="tiny primary"
          onClick={addCandidate}
          disabled={!draftProvider || !draftModel.trim()}
        >
          添加
        </button>
      </div>
    </div>
  );
}
