export function DomainRiskList({ risks }: { risks: string[] }) {
  return (
    <section className="domain-panel">
      <div className="domain-panel-head">
        <h2>注意事项</h2>
        <span>兼容旧工作流</span>
      </div>
      <ul className="domain-list">
        {risks.map((risk) => (
          <li key={risk}>{risk}</li>
        ))}
      </ul>
    </section>
  );
}
