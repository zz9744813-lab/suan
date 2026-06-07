import "./Spinner.css";

export type SpinnerProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
};

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      className={["ui-spinner", `ui-spinner--${size}`, className].join(" ")}
      role="status"
      aria-label="加载中"
    >
      <div className="ui-spinner__ring" />
    </div>
  );
}
