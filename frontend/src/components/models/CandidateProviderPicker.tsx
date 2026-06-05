/**
 * CandidateProviderPicker — 候选 Provider 多选器
 *
 * 显示所有已启用的 Provider，允许勾选
 */

interface ProviderItem {
  id: number;
  name: string;
  enabled: boolean;
}

interface Props {
  providerIds: number[];
  onChange: (ids: number[]) => void;
  providers: ProviderItem[];
}

export function CandidateProviderPicker({ providerIds, onChange, providers }: Props) {
  const enabledProviders = providers.filter((p) => p.enabled);

  function toggle(id: number) {
    if (providerIds.includes(id)) {
      onChange(providerIds.filter((x) => x !== id));
    } else {
      onChange([...providerIds, id]);
    }
  }

  if (enabledProviders.length === 0) {
    return <div className="muted small">无可用 Provider</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {enabledProviders.map((p) => (
        <label key={p.id} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={providerIds.includes(p.id)}
            onChange={() => toggle(p.id)}
          />
          <span className="small">{p.name} (#{p.id})</span>
        </label>
      ))}
    </div>
  );
}
