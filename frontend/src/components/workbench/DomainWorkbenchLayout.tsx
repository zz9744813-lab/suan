import { DomainBreadcrumb } from "../layout/DomainBreadcrumb";
import type { DomainConfig, DomainMetric } from "../../lib/domainMap";
import { useProjectStore } from "../../stores/projectStore";
import { useWorkbenchOverview } from "../../hooks/useWorkbenchOverview";
import { DomainHero } from "./DomainHero";
import { DomainMetricStrip } from "./DomainMetricStrip";
import { DomainRiskList } from "./DomainRiskList";
import { DomainActionList } from "./DomainActionList";
import { DomainDrilldownGrid } from "./DomainDrilldownGrid";
import "./DomainWorkbench.css";

export function DomainWorkbenchLayout({ domain }: { domain: DomainConfig }) {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const { data: overview, loading, error } = useWorkbenchOverview({ projectId: currentProjectId, domain: domain.key, refreshMs: 8000 });
  const liveDomain = overview?.domains?.find((item) => item.key === domain.key);
  const metrics: DomainMetric[] = liveDomain?.metrics?.length
    ? liveDomain.metrics.map((metric) => ({
        label: metric.label,
        value: formatMetricValue(metric.value, metric.unit),
        hint: liveDomain.status,
      }))
    : domain.metrics;
  const actions = liveDomain?.actions?.length
    ? liveDomain.actions.map((action) => action.label)
    : overview?.recommended_actions?.length
      ? overview.recommended_actions.filter((action) => action.domain === domain.key).map((action) => action.label)
      : domain.actions;
  const risks = liveDomain?.risks?.length
    ? liveDomain.risks.map((risk) => `${risk.title}：${risk.summary}`)
    : overview?.risks?.length
      ? overview.risks.filter((risk) => risk.domain === domain.key).map((risk) => `${risk.title}：${risk.summary}`)
      : domain.risks;

  return (
    <div className="domain-workbench-page">
      <DomainBreadcrumb current={domain.label} links={domain.drilldowns} />
      <DomainHero domain={domain} />
      <div className="domain-live-state">
        <span>{loading ? "正在同步实时概览…" : liveDomain ? `实时状态：${liveDomain.status}` : "使用静态入口配置"}</span>
        {overview?.as_of && <time>更新：{new Date(overview.as_of).toLocaleTimeString("zh-CN")}</time>}
        {error && <em>实时概览读取失败：{error}</em>}
      </div>
      <DomainMetricStrip metrics={metrics} />
      <div className="domain-workbench-grid">
        <DomainActionList actions={actions.length ? actions : domain.actions} />
        <DomainRiskList risks={risks.length ? risks : domain.risks} />
      </div>
      <DomainDrilldownGrid links={domain.drilldowns} />
    </div>
  );
}

function formatMetricValue(value: number | string | null, unit: string | null) {
  if (value == null || value === "") return "—";
  if (unit === "$") return `$${value}`;
  return `${value}${unit ?? ""}`;
}
