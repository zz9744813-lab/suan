import type { DomainMetric } from "../../lib/domainMap";

export function DomainMetricStrip({ metrics }: { metrics: DomainMetric[] }) {
  return (
    <section className="domain-metric-strip" aria-label="域指标">
      {metrics.map((metric) => (
        <div key={metric.label} className="domain-metric-card">
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <small>{metric.hint}</small>
        </div>
      ))}
    </section>
  );
}
