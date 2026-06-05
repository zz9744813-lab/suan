/**
 * FallbackCandidateEditor — Fallback 候选编辑器
 *
 * 编辑 fallback_candidates_json 的 Provider/Model 对列表
 */
import { useState } from "react";

interface FallbackCandidate {
  provider_id: number;
  model_name: string;
}

interface Props {
  candidates: FallbackCandidate[];
  onChange: (c: FallbackCandidate[]) => void;
  allowAutoFallback: boolean;
  onAllowChange: (v: boolean) => void;
}

export function FallbackCandidateEditor({ candidates, onChange, allowAutoFallback, onAllowChange }: Props) {
  const [draftProvider, setDraftProvider] = useState("");
  const [draftModel, setDraftModel] = useState("");

  function addCandidate() {
    const pid = Number(draftProvider);
    const model = draftModel.trim();
    if (!pid || !model) return;
    onChange([...candidates, { provider_id: pid, model_name: model }]);
    setDraftProvider("");
    setDraftModel("");
  }

  function removeCandidate(index: number) {
    onChange(candidates.filter((_, i) => i !== index));
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
              <th className="muted small" style={{ textAlign: "left", padding: "2px 6px" }}>Provider ID</th>
              <th className="muted small" style={{ textAlign: "left", padding: "2px 6px" }}>Model</th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c, i) => (
              <tr key={i}>
                <td style={{ padding: "2px 6px" }}>{c.provider_id}</td>
                <td style={{ padding: "2px 6px" }}>{c.model_name}</td>
                <td><button className="tiny" onClick={() => removeCandidate(i)} title="移除">✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        <input
          className="input"
          placeholder="Provider ID"
          value={draftProvider}
          onChange={(e) => setDraftProvider(e.target.value)}
          style={{ width: 100 }}
        />
        <input
          className="input"
          placeholder="Model 名称"
          value={draftModel}
          onChange={(e) => setDraftModel(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addCandidate(); }}
          style={{ flex: 1 }}
        />
        <button className="tiny primary" onClick={addCandidate} disabled={!draftProvider || !draftModel.trim()}>添加</button>
      </div>
    </div>
  );
}
