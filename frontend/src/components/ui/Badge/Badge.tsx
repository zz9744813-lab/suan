import "./Badge.css";

export type Tone = "default" | "info" | "success" | "warning" | "danger" | "purple";

export type BadgeProps = {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
};

const toneClass: Record<Tone, string> = {
  default: "ui-badge--default",
  info: "ui-badge--info",
  success: "ui-badge--success",
  warning: "ui-badge--warning",
  danger: "ui-badge--danger",
  purple: "ui-badge--purple",
};

export function Badge({ tone = "default", children, className = "" }: BadgeProps) {
  return (
    <span className={["ui-badge", toneClass[tone], className].join(" ")}>
      {children}
    </span>
  );
}
