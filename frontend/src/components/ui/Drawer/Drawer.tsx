import { useEffect, useRef } from "react";
import "./Drawer.css";

export type DrawerProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  width?: number | string;
  className?: string;
};

export function Drawer({
  open,
  onClose,
  title,
  children,
  width = 400,
  className = "",
}: DrawerProps) {
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      previousFocus.current = document.activeElement as HTMLElement;
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
      previousFocus.current?.focus();
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ui-drawer-backdrop" onClick={onClose}>
      <aside
        className={["ui-drawer", className].join(" ")}
        style={{ width }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="ui-drawer__header">
            <h2 className="ui-drawer__title">{title}</h2>
            <button className="ui-drawer__close" onClick={onClose} aria-label="关闭" type="button">×</button>
          </div>
        )}
        <div className="ui-drawer__body">{children}</div>
      </aside>
    </div>
  );
}
