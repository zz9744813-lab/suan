import { DomainBreadcrumb } from "../layout/DomainBreadcrumb";
import type { DomainConfig } from "../../lib/domainMap";
import { DomainHero } from "./DomainHero";
import { DomainMetricStrip } from "./DomainMetricStrip";
import { DomainRiskList } from "./DomainRiskList";
import { DomainActionList } from "./DomainActionList";
import { DomainDrilldownGrid } from "./DomainDrilldownGrid";
import "./DomainWorkbench.css";

export function DomainWorkbenchLayout({ domain }: { domain: DomainConfig }) {
  return (
    <div className="domain-workbench-page">
      <DomainBreadcrumb current={domain.label} links={domain.drilldowns} />
      <DomainHero domain={domain} />
      <DomainMetricStrip metrics={domain.metrics} />
      <div className="domain-workbench-grid">
        <DomainActionList actions={domain.actions} />
        <DomainRiskList risks={domain.risks} />
      </div>
      <DomainDrilldownGrid links={domain.drilldowns} />
    </div>
  );
}
