import "./Card.css";

export type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "elevated" | "flat";
  padding?: "none" | "sm" | "md" | "lg";
};

export function Card({
  className = "",
  variant = "default",
  padding = "md",
  ...props
}: CardProps) {
  return (
    <div
      className={[
        "ui-card",
        `ui-card--${variant}`,
        `ui-card--padding-${padding}`,
        className,
      ].join(" ")}
      {...props}
    />
  );
}
