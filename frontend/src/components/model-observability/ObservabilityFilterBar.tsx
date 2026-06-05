import { useEffect, useState } from "react";
import { listAgentRoles, listProviders } from "../../api";

export type ObservabilityFilters = {
  range: "15m" | "1h" | "6h" | "24h" | "7d";
  project_id?: number;
  agent_role_key?: string;
  provider_id?: number;
  model_name?: string;
  status?: "all" | "success" | "failed" | "fallback" | "slow" | "costly";
};

type Props = {
  filters: ObservabilityFilters;
  onChange: (f: ObservabilityFilters) => void;
};

const RANGES: ObservabilityFilters["range"][] = ["15m", "1h", "6h", "24h", "7d"];
const STATUS_OPTIONS: { value: ObservabilityFilters["status"]; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "success", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "fallback", label: "Fallback" },
  { value: "slow", label: "慢" },
  { value: "costly", label: "高成本" },
];

export function ObservabilityFilterBar({ filters, onChange }: Props) {
  const [agentRoles, setAgentRoles] = useState<any[]>([]);
  const [providerList, setProviderList] = useState<any[]>([]);
  const [modelList, setModelList] = useState<string[]>([]);

  useEffect(() => {
    listAgentRoles({ enabled_only: true }).then((r: any) => {
      setAgentRoles(Array.isArray(r) ? r : r?.items ?? []);
    }).catch(() => {});
    listProviders().then((r: any) => {
      setProviderList(Array.isArray(r) ? r : []);
    }).catch(() => {});
  }, []);

  // 从 provider 列表中提取去重 model 名
  useEffect(() => {
    const models = new Set<string>();
    providerList.forEach((p: any) => {
      if (p.default_model) models.add(p.default_model);
      if (Array.isArray(p.models)) p.models.forEach((m: string) => models.add(m));
    });
    setModelList(Array.from(models).sort());
  }, [providerList]);

  const set = (patch: Partial<ObservabilityFilters>) =>
    onChange({ ...filters, ...patch });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "8px 0" }}>
      {/* 时间范围 */}
      <div style={{ display: "flex", gap: 2 }}>
        {RANGES.map((r) => (
          <button
            key={r}
            className="tiny"
            style={filters.range === r ? { background: "var(--primary)", color: "#fff" } : {}}
            onClick={() => set({ range: r })}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Agent */}
      <select
        className="input"
        style={{ minWidth: 120, fontSize: 12 }}
        value={filters.agent_role_key ?? ""}
        onChange={(e) => set({ agent_role_key: e.target.value || undefined })}
      >
        <option value="">全部 Agent</option>
        {agentRoles.map((a: any) => (
          <option key={a.key ?? a.id} value={a.key}>
            {a.display_name ?? a.key}
          </option>
        ))}
      </select>

      {/* Provider */}
      <select
        className="input"
        style={{ minWidth: 120, fontSize: 12 }}
        value={filters.provider_id ?? ""}
        onChange={(e) => set({ provider_id: e.target.value ? Number(e.target.value) : undefined })}
      >
        <option value="">全部 Provider</option>
        {providerList.map((p: any) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

      {/* Model */}
      <select
        className="input"
        style={{ minWidth: 140, fontSize: 12 }}
        value={filters.model_name ?? ""}
        onChange={(e) => set({ model_name: e.target.value || undefined })}
      >
        <option value="">全部 Model</option>
        {modelList.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>

      {/* 状态 */}
      <div style={{ display: "flex", gap: 4 }}>
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s.value}
            className="pill"
            style={(filters.status ?? "all") === s.value ? { background: "var(--primary)", color: "#fff" } : {}}
            onClick={() => set({ status: s.value })}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
