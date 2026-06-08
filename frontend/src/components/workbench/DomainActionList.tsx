export function DomainActionList({ actions }: { actions: string[] }) {
  return (
    <section className="domain-panel">
      <div className="domain-panel-head">
        <h2>推荐动作</h2>
        <span>下一步</span>
      </div>
      <ol className="domain-action-list">
        {actions.map((action) => (
          <li key={action}>{action}</li>
        ))}
      </ol>
    </section>
  );
}
