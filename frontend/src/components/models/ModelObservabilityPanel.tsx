import { useState, useEffect, useCallback } from "react";
import {
  getObservabilitySummary,
  getObservabilityEvents,
  getObservabilityProviders,
  getObservabilityModels,
  getObservabilityAgents,
  getObservabilityFailures,
  getObservabilitySlowRequests,
} from "../../api";
import { ObservabilityFilterBar } from "../model-observability/ObservabilityFilterBar";
import type { ObservabilityFilters } from "../model-observability/ObservabilityFilterBar";
import { ObservabilityKpiGrid } from "../model-observability/ObservabilityKpiGrid";
import { ProviderHealthTable } from "../model-observability/ProviderHealthTable";
import { ModelHealthTable } from "../model-observability/ModelHealthTable";
import { AgentCallMatrix } from "../model-observability/AgentCallMatrix";
import { FailureReasonChart } from "../model-observability/FailureReasonChart";
import { ObservabilityEventStream } from "../model-observability/ObservabilityEventStream";
import { EventDetailDrawer } from "../model-observability/EventDetailDrawer";
import { SlowRequestList } from "../model-observability/SlowRequestList";
import { FallbackTimeline } from "../model-observability/FallbackTimeline";

const RANGE_HOURS: Record<ObservabilityFilters["range"], number> = {
  "15m": 0.25,
  "1h": 1,
  "6h": 6,
  "24h": 24,
  "7d": 168,
};

export default function ModelObservabilityPanel({ projectId }: { projectId?: number }) {
  const [filters, setFilters] = useState<ObservabilityFilters>({ range: "24h" });
  const [summary, setSummary] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [failures, setFailures] = useState<any[]>([]);
  const [slowRequests, setSlowRequests] = useState<any[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const [expandedProvider, setExpandedProvider] = useState<number | null>(null);
  const [providerModelStats, setProviderModelStats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMoreEvents, setHasMoreEvents] = useState(false);
  const [eventOffset, setEventOffset] = useState(0);

  const hours = RANGE_HOURS[filters.range] ?? 24;

  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      const [sRes, pRes, mRes, aRes, fRes, slowRes] = await Promise.all([
        getObservabilitySummary().catch(() => null),
        getObservabilityProviders().catch(() => []),
        getObservabilityModels({ hours }).catch(() => []),
        getObservabilityAgents({ hours, project_id: projectId }).catch(() => []),
        getObservabilityFailures({ hours, limit: 200 }).catch(() => []),
        getObservabilitySlowRequests({ hours, threshold_ms: 5000, limit: 50 }).catch(() => []),
      ]);
      setSummary(sRes);
      setProviders(Array.isArray(pRes) ? pRes : []);
      setModels(Array.isArray(mRes) ? mRes : []);
      setAgents(Array.isArray(aRes) ? aRes : []);
      setFailures(Array.isArray(fRes) ? fRes : []);
      setSlowRequests(Array.isArray(slowRes) ? slowRes : []);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [hours, projectId]);

  // 加载事件
  const loadEvents = useCallback(async (offset = 0) => {
    try {
      const eRes = await getObservabilityEvents({
        limit: 50,
        provider_id: filters.provider_id,
        model_name: filters.model_name,
      });
      const arr = Array.isArray(eRes) ? eRes : [];
      if (offset === 0) {
        setEvents(arr);
      } else {
        setEvents((prev) => [...prev, ...arr]);
      }
      setHasMoreEvents(arr.length >= 50);
      setEventOffset(offset + arr.length);
    } catch {
      // silently fail
    }
  }, [filters.provider_id, filters.model_name]);

  useEffect(() => {
    loadAll();
    loadEvents(0);
  }, [loadAll, loadEvents]);

  // 自动刷新
  useEffect(() => {
    const id = window.setInterval(() => {
      loadAll();
      loadEvents(0);
    }, 15000);
    return () => window.clearInterval(id);
  }, [loadAll, loadEvents]);

  // 展开 Provider 模型
  const handleExpandProvider = (providerId: number) => {
    if (expandedProvider === providerId) {
      setExpandedProvider(null);
      setProviderModelStats([]);
      return;
    }
    setExpandedProvider(providerId);
    // 过滤当前 models 列表中属于该 provider 的
    const filtered = models.filter((m: any) => m.provider_id === providerId);
    setProviderModelStats(filtered);
  };

  // 事件详情
  const handleClickEvent = (eventId: number) => {
    const ev = events.find((e: any) => e.id === eventId);
    if (ev) setSelectedEvent(ev);
  };

  // Agent 点击 → 过滤
  const handleClickAgent = (agentRoleKey: string) => {
    setFilters((prev) => ({ ...prev, agent_role_key: agentRoleKey }));
  };

  // 加载更多事件
  const handleLoadMoreEvents = () => {
    loadEvents(eventOffset);
  };

  // Fallback 事件
  const fallbackEvents = events.filter(
    (ev: any) => ev.is_fallback || ev.event_type === "fallback",
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: "0 4px" }}>
      <ObservabilityFilterBar filters={filters} onChange={setFilters} />
      <ObservabilityKpiGrid summary={summary} loading={loading} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="card-header">
            <h3>Provider 健康</h3>
          </div>
          <div style={{ padding: 8 }}>
            <ProviderHealthTable
              providers={providers}
              loading={loading}
              onExpand={handleExpandProvider}
              expandedId={expandedProvider}
              modelStats={providerModelStats}
            />
          </div>
        </div>

        <div className="card" style={{ overflow: "hidden" }}>
          <div className="card-header">
            <h3>Model 健康</h3>
          </div>
          <div style={{ padding: 8 }}>
            <ModelHealthTable models={models} loading={loading} />
          </div>
        </div>
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        <div className="card-header">
          <h3>Agent 调用矩阵</h3>
        </div>
        <div style={{ padding: 12 }}>
          <AgentCallMatrix agents={agents} loading={loading} onClickAgent={handleClickAgent} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="card-header">
            <h3>失败原因分布</h3>
          </div>
          <div style={{ padding: 12 }}>
            <FailureReasonChart failures={failures} loading={loading} />
          </div>
        </div>

        <div className="card" style={{ overflow: "hidden" }}>
          <div className="card-header">
            <h3>Fallback 时间线</h3>
          </div>
          <div style={{ padding: 12, maxHeight: 300, overflowY: "auto" }}>
            <FallbackTimeline events={fallbackEvents} loading={loading} />
          </div>
        </div>
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        <div className="card-header">
          <h3>事件流</h3>
          <span className="muted small">{events.length} 条</span>
        </div>
        <div style={{ padding: 8 }}>
          <ObservabilityEventStream
            events={events}
            loading={loading}
            onLoadMore={handleLoadMoreEvents}
            hasMore={hasMoreEvents}
            onClickEvent={handleClickEvent}
          />
        </div>
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        <div className="card-header">
          <h3>慢请求</h3>
        </div>
        <div style={{ padding: 8 }}>
          <SlowRequestList events={slowRequests} loading={loading} />
        </div>
      </div>

      <EventDetailDrawer
        visible={!!selectedEvent}
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
      />
    </div>
  );
}
