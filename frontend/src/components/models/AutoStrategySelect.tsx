/**
 * AutoStrategySelect — 自动策略选择下拉
 *
 * quality_first / cost_first / speed_first / long_context_first / json_stable_first
 */

const STRATEGIES = [
  { value: "quality_first", label: "质量优先" },
  { value: "cost_first", label: "成本优先" },
  { value: "speed_first", label: "速度优先" },
  { value: "long_context_first", label: "长上下文" },
  { value: "json_stable_first", label: "JSON稳定" },
] as const;

interface Props {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}

export function AutoStrategySelect({ value, onChange, disabled }: Props) {
  return (
    <select
      className="input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      style={{ minWidth: 140 }}
    >
      {STRATEGIES.map((s) => (
        <option key={s.value} value={s.value}>
          {s.label}
        </option>
      ))}
    </select>
  );
}
