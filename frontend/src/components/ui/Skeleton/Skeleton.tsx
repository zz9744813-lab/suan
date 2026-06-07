import "./Skeleton.css";

export type SkeletonProps = {
  width?: number | string;
  height?: number | string;
  radius?: "sm" | "md" | "lg";
  className?: string;
};

export function Skeleton({
  width = "100%",
  height = 16,
  radius = "md",
  className = "",
}: SkeletonProps) {
  return (
    <div
      className={["ui-skeleton", `ui-skeleton--${radius}`, className].join(" ")}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}
