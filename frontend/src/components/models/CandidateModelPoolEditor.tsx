/**
 * CandidateModelPoolEditor — 候选模型池编辑器
 *
 * 显示当前候选模型列表，支持添加/删除
 */
import { useState } from "react";

interface Props {
  models: string[];
  onChange: (models: string[]) => void;
}

export function CandidateModelPoolEditor({ models, onChange }: Props) {
  const [draft, setDraft] = useState("");

  function addModel() {
    const trimmed = draft.trim();
    if (!trimmed || models.includes(trimmed)) return;
    onChange([...models, trimmed]);
    setDraft("");
  }

  function removeModel(name: string) {
    onChange(models.filter((m) => m !== name));
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
        <input
          className="input"
          placeholder="模型名称，如 gpt-4o"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addModel(); }}
          style={{ flex: 1 }}
        />
        <button className="tiny primary" onClick={addModel} disabled={!draft.trim()}>添加</button>
      </div>
      {models.length === 0 ? (
        <div className="muted small">暂无候选模型</div>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 3 }}>
          {models.map((m) => (
            <li key={m} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="small" style={{ flex: 1 }}>{m}</span>
              <button className="tiny" onClick={() => removeModel(m)} title="移除">✕</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
