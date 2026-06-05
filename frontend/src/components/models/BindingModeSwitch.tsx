type BindingMode = "auto" | "manual_with_fallback" | "locked";

interface Props {
  value: BindingMode;
  onChange: (v: BindingMode) => void;
  disabled?: boolean;
}

export function BindingModeSwitch({ value, onChange, disabled }: Props) {
  const modes: { key: BindingMode; label: string; icon: string }[] = [
    { key: "auto", label: "自动", icon: "A" },
    { key: "manual_with_fallback", label: "手动+备用", icon: "M" },
    { key: "locked", label: "锁定", icon: "L" },
  ];

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {modes.map((mode) => (
        <button
          key={mode.key}
          type="button"
          className={`tiny ${value === mode.key ? "primary" : ""}`}
          disabled={disabled}
          onClick={() => onChange(mode.key)}
          title={mode.label}
        >
          {mode.icon} {mode.label}
        </button>
      ))}
    </div>
  );
}
