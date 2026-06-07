import "./EmptyState.css";

export type EmptyStateProps = {
  title: string;
  description?: string;
  action?: React.ReactNode;
};

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="ui-empty-state">
      <div className="ui-empty-state__mark" aria-hidden="true">◇</div>
      <h3 className="ui-empty-state__title">{title}</h3>
      {description && <p className="ui-empty-state__desc">{description}</p>}
      {action && <div className="ui-empty-state__action">{action}</div>}
    </div>
  );
}
