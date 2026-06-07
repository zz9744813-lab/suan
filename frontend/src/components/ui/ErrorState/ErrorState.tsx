import "./ErrorState.css";

export type ErrorStateProps = {
  title?: string;
  message?: string;
  onRetry?: () => void;
};

export function ErrorState({
  title = "加载失败",
  message = "请求过程中出现错误，请稍后重试。",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="ui-error-state" role="alert">
      <div className="ui-error-state__icon" aria-hidden="true">⚠</div>
      <h3 className="ui-error-state__title">{title}</h3>
      <p className="ui-error-state__message">{message}</p>
      {onRetry && (
        <button className="ui-error-state__retry" onClick={onRetry} type="button">
          重试
        </button>
      )}
    </div>
  );
}
