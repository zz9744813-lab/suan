import type { DomainConfig } from "../../lib/domainMap";

export function DomainHero({ domain }: { domain: DomainConfig }) {
  return (
    <section className="domain-hero">
      <div className="domain-hero-icon" aria-hidden="true">{domain.navIcon}</div>
      <div>
        <div className="domain-hero-eyebrow">{domain.eyebrow}</div>
        <h1>{domain.title}</h1>
        <p>{domain.description}</p>
      </div>
    </section>
  );
}
