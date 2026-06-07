import "./Pill.css";

export type PillProps = {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
};

export function Pill({ active = false, children, onClick, className = "" }: PillProps) {
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      className={["ui-pill", active ? "ui-pill--active" : "", className].filter(Boolean).join(" ")}
      {...(onClick ? { onClick, type: "button" as const } : {})}
    >
      {children}
    </Tag>
  );
}
