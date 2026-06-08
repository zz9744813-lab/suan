import { Link } from "react-router-dom";
import type { DomainLink } from "../../lib/domainMap";

export function DomainDrilldownGrid({ links }: { links: DomainLink[] }) {
  return (
    <section className="domain-drilldowns">
      <div className="domain-section-title">
        <h2>专业入口</h2>
        <span>旧页面仍可直接打开，这里只做收束和下钻。</span>
      </div>
      <div className="domain-drilldown-grid">
        {links.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className={`domain-drilldown-card domain-drilldown-${link.tone ?? "normal"}`}
          >
            <strong>{link.label}</strong>
            <span>{link.description}</span>
            <em>{link.to}</em>
          </Link>
        ))}
      </div>
    </section>
  );
}
