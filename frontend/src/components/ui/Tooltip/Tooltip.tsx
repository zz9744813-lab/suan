import { useState, useRef } from "react";
import "./Tooltip.css";

export type TooltipProps = {
  content: string;
  children: React.ReactNode;
  className?: string;
};

export function Tooltip({ content, children, className = "" }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timeout = useRef<ReturnType<typeof setTimeout>>();

  const show = () => {
    clearTimeout(timeout.current);
    timeout.current = setTimeout(() => setVisible(true), 300);
  };
  const hide = () => {
    clearTimeout(timeout.current);
    timeout.current = setTimeout(() => setVisible(false), 100);
  };

  return (
    <div
      className={["ui-tooltip-wrap", className].join(" ")}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {visible && (
        <div className="ui-tooltip" role="tooltip">
          {content}
        </div>
      )}
    </div>
  );
}
