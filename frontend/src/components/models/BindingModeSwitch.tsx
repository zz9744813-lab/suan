/**
 * BindingModeSwitch — 模型绑定模式切换组件
 *
 * 三种模式: auto / manual / manual_with_fallback
 */
type BindingMode = "auto" | "manual" | "manual_with_fallback";

interface Props {
  value: BindingMode;
  onChange: (v: BindingMode) => void;
  disabled?: boolean;
}

export function BindingModeSwitch({ value, onChange, disabled }: Props) {
  const modes: { key: BindingMode; label: string; icon: string }[] = [
    { key: "auto", label: "自动选择", icon: "⚡" },
    { key: "manual", label: "手动锁定", icon: "🔒" },
    { key: "manual_with_fallback", label: "手动+备用", icon: "🔀" },
  ];
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {modes.map((m) => (
        <button
          key={m.key}
          className={`tiny ${value === m.key ? "primary" : ""}`}
          disabled={disabled}
          onClick={() => onChange(m.key)}
          title={m.label}
        >
          {m.icon} {m.label}
        </button>
      ))}
    </div>
  );
}
