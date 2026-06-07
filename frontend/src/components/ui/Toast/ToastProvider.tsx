import { useToastStore } from "./ToastStore";
import "./Toast.css";

export function ToastProvider() {
  const items = useToastStore((s) => s.items);
  const remove = useToastStore((s) => s.remove);

  if (items.length === 0) return null;

  return (
    <div className="ui-toast-viewport" aria-live="polite" aria-atomic="true">
      {items.map((t) => (
        <div key={t.id} className={`ui-toast ui-toast--${t.tone}`}>
          <div className="ui-toast__content">
            <strong className="ui-toast__title">{t.title}</strong>
            {t.description && (
              <p className="ui-toast__desc">{t.description}</p>
            )}
          </div>
          <button
            className="ui-toast__close"
            onClick={() => remove(t.id)}
            aria-label="关闭通知"
            type="button"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
