import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { testProvider } from "../api";

interface ProviderInfo {
  id: number; name: string; base_url: string;
  enabled: boolean; default_model: string;
  model_count: number; is_stub: boolean;
}

interface ModelItem {
  model_name: string; status: string; health_score: number;
  success_rate: number; avg_latency_ms: number;
  supports_json: boolean; supports_text: boolean;
  last_error_message: string | null; probe_count: number;
  consecutive_failures: number;
  input_price_per_million: number | null;
  output_price_per_million: number | null;
}

interface RouteEvent {
  id: number; agent_role_key: string; binding_mode: string;
  selected_model_name: string; route_reason: string;
  locked: boolean; fallback_used: boolean;
  health_score: number | null; error_message: string | null;
  created_at: string;
}

interface BoundAgent {
  role_id: number; role_key: string; display_name: string;
  binding_mode: string; model_name: string; is_locked: boolean;
}

interface ProviderDetail {
  provider: ProviderInfo;
  models: ModelItem[];
  route_events: RouteEvent[];
  bound_agents: BoundAgent[];
}

const STATUS_COLORS: Record<string, string> = {
  healthy: "#22c55e", degraded: "#f59e0b", rate_limited: "#f97316",
  failing: "#ef4444", disabled: "#94a3b8", unknown: "#64748b", mock: "#6366f1",
};
const STATUS_LABELS: Record<string, string> = {
  healthy: "可用", degraded: "降级", rate_limited: "限流",
  failing: "失败", disabled: "禁用", unknown: "未知", mock: "模拟",
};

type Tab = "models" | "fallback" | "records" | "bindings" | "settings";

export default function ModelProviderDetailPage() {
  const { providerId } = useParams<{ providerId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<ProviderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("models");
  const [probing, setProbing] = useState(false);
  const [pullingModels, setPullingModels] = useState(false);
  const [probeResults, setProbeResults] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");

  const fetchDetail = async () => {
    try {
      const detail = await api.get<ProviderDetail>(
        `/api/model-control/providers/${providerId}`
      );
      setData(detail);
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDetail(); }, [providerId]);

  const probeAll = async () => {
    setProbing(true);
    setError("");
    setNotice("");
    try {
      await api.post(`/api/model-control/providers/${providerId}/probe-all`);
      await fetchDetail();
    } catch (e: any) {
      setError(e?.message || "探测失败");
    } finally {
      setProbing(false);
    }
  };

  const pullModels = async () => {
    if (!providerId) return;
    setPullingModels(true);
    setError("");
    setNotice("");
    try {
      const result = await testProvider(Number(providerId));
      if (!result.ok) {
        throw new Error(result.suggestion ? `${result.message}；${result.suggestion}` : result.message);
      }
      setNotice(`已拉取 ${result.models.length} 个模型`);
      await fetchDetail();
    } catch (e: any) {
      setError(e?.message || "拉取模型列表失败");
    } finally {
      setPullingModels(false);
    }
  };

  const probeOne = async (modelName: string) => {
    setProbeResults((prev) => ({ ...prev, [modelName]: "probing..." }));
    try {
      const r = await api.post<any>(
        `/api/model-control/providers/${providerId}/models/${encodeURIComponent(modelName)}/probe`
      );
      setProbeResults((prev) => ({
        ...prev,
        [modelName]: `${r.status} (${r.latency_ms}ms, score:${r.health_score})`,
      }));
    } catch {
      setProbeResults((prev) => ({ ...prev, [modelName]: "probe failed" }));
    }
  };

  if (loading) return <div style={{ padding: 24, color: "#94a3b8" }}>加载中...</div>;
  if (error) return <div style={{ padding: 24, color: "#ef4444" }}>{error}</div>;
  if (!data) return null;

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <button
            onClick={() => navigate("/models")}
            style={{ background: "none", border: "none", color: "#6366f1", cursor: "pointer", fontSize: 12, marginBottom: 8 }}
          >
            ← 返回
          </button>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>{data.provider.name}</h1>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
            模型 {data.provider.model_count} · {data.provider.base_url}
            {data.provider.is_stub && <span style={{ color: "#f59e0b", marginLeft: 8 }}>模拟 Provider</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={pullModels} disabled={pullingModels} style={{
            padding: "6px 14px", borderRadius: 6, border: "1px solid #334155",
            background: "#1e293b", color: "#e2e8f0", cursor: pullingModels ? "not-allowed" : "pointer",
            fontSize: 12,
          }}>
            {pullingModels ? "拉取中..." : "拉取模型列表"}
          </button>
          <button onClick={probeAll} disabled={probing} style={{
            padding: "6px 14px", borderRadius: 6, border: "1px solid #334155",
            background: "#1e293b", color: "#e2e8f0", cursor: probing ? "not-allowed" : "pointer",
            fontSize: 12,
          }}>
            {probing ? "探测中..." : "测试全部"}
          </button>
          <button onClick={fetchDetail} style={{
            padding: "6px 14px", borderRadius: 6, border: "1px solid #334155",
            background: "#1e293b", color: "#e2e8f0", cursor: "pointer", fontSize: 12,
          }}>
            刷新
          </button>
        </div>
      </div>

      {notice && (
        <div style={{
          marginBottom: 12, padding: "8px 12px", borderRadius: 6,
          border: "1px solid rgba(34,197,94,0.35)", color: "#22c55e",
          background: "rgba(34,197,94,0.08)", fontSize: 12,
        }}>
          {notice}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, marginBottom: 20, borderBottom: "1px solid #334155" }}>
        {(["models", "fallback", "records", "bindings", "settings"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "8px 18px", border: "none", background: "none",
              color: tab === t ? "#e2e8f0" : "#64748b", cursor: "pointer",
              borderBottom: tab === t ? "2px solid #6366f1" : "2px solid transparent",
              fontSize: 13, fontWeight: tab === t ? 600 : 400,
            }}
          >
            {{ models: "模型", fallback: "Fallback", records: "调用记录", bindings: "绑定 Agent", settings: "设置" }[t]}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "models" && (
        <ModelsTab models={data.models} probeOne={probeOne} probeResults={probeResults} />
      )}
      {tab === "records" && (
        <RecordsTab events={data.route_events} />
      )}
      {tab === "bindings" && (
        <BindingsTab agents={data.bound_agents} />
      )}
      {tab === "fallback" && (
        <div style={{ color: "#94a3b8", fontSize: 13, padding: "20px 0" }}>
          Fallback 策略 — 在 Agent 绑定抽屉中配置
        </div>
      )}
      {tab === "settings" && (
        <div style={{ color: "#94a3b8", fontSize: 13, padding: "20px 0" }}>
          Provider 设置 — 返回 Provider 列表编辑
        </div>
      )}
    </div>
  );
}

function ModelsTab({
  models, probeOne, probeResults,
}: {
  models: ModelItem[];
  probeOne: (name: string) => void;
  probeResults: Record<string, string>;
}) {
  if (models.length === 0) {
    return <div style={{ color: "#64748b", fontSize: 13, padding: "20px 0" }}>暂无模型数据，请先「拉取模型列表」</div>;
  }
  return (
    <div>
      {models.map((m) => (
        <div key={m.model_name} style={{
          background: "#1e293b", borderRadius: 8, padding: "12px 16px",
          marginBottom: 8, border: "1px solid #334155",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontWeight: 600, color: "#f1f5f9", fontSize: 13 }}>{m.model_name}</span>
              <span style={{
                fontSize: 10, padding: "1px 6px", borderRadius: 4,
                color: STATUS_COLORS[m.status] || "#94a3b8",
                background: (STATUS_COLORS[m.status] || "#94a3b8") + "18",
              }}>
                {STATUS_LABELS[m.status] || m.status}
              </span>
              {m.supports_json && <span style={{ fontSize: 9, color: "#22c55e", background: "#064e3b", padding: "1px 4px", borderRadius: 3 }}>JSON</span>}
              {!m.supports_text && <span style={{ fontSize: 9, color: "#f59e0b", background: "#422006", padding: "1px 4px", borderRadius: 3 }}>非文本</span>}
            </div>
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
              成功率 {m.success_rate.toFixed(0)}% · 延迟 {m.avg_latency_ms}ms · 探针 {m.probe_count}次
              {m.consecutive_failures > 0 && <span style={{ color: "#ef4444" }}> · 连续失败 {m.consecutive_failures}</span>}
              {m.input_price_per_million != null && (
                <span> · ${m.input_price_per_million.toFixed(2)}/M in</span>
              )}
            </div>
            {m.last_error_message && (
              <div style={{ fontSize: 10, color: "#ef4444", marginTop: 2 }}>{m.last_error_message.slice(0, 80)}</div>
            )}
          </div>
          <div style={{ textAlign: "right", marginLeft: 16 }}>
            <div style={{
              fontSize: 18, fontWeight: 700,
              color: m.health_score >= 0.8 ? "#22c55e" : m.health_score >= 0.5 ? "#f59e0b" : "#ef4444",
            }}>
              {(m.health_score * 100).toFixed(0)}
            </div>
            <div style={{ fontSize: 9, color: "#64748b" }}>健康分</div>
            <button
              onClick={() => probeOne(m.model_name)}
              style={{
                marginTop: 4, padding: "3px 10px", borderRadius: 4,
                border: "1px solid #475569", background: "#0f172a",
                color: "#e2e8f0", cursor: "pointer", fontSize: 11,
              }}
            >测试</button>
            {probeResults[m.model_name] && (
              <div style={{ fontSize: 9, color: "#94a3b8", marginTop: 2 }}>{probeResults[m.model_name]}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function RecordsTab({ events }: { events: RouteEvent[] }) {
  if (events.length === 0) {
    return <div style={{ color: "#64748b", fontSize: 13, padding: "20px 0" }}>暂无调用记录</div>;
  }
  return (
    <div>
      {events.map((e) => (
        <div key={e.id} style={{
          background: "#1e293b", borderRadius: 8, padding: "10px 16px",
          marginBottom: 6, border: "1px solid #334155", fontSize: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "#e2e8f0" }}>{e.agent_role_key}</span>
            <span style={{ color: "#64748b" }}>
              {e.fallback_used && <span style={{ color: "#f59e0b", marginRight: 8 }}>Fallback</span>}
              {e.locked && <span style={{ color: "#f59e0b", marginRight: 8 }}>锁定</span>}
              {e.created_at}
            </span>
          </div>
          <div style={{ color: "#94a3b8" }}>
            {e.selected_model_name} · {e.route_reason}
            {e.health_score != null ? ` · 健康分 ${e.health_score.toFixed(2)}` : ""}
          </div>
          {e.error_message && <div style={{ color: "#ef4444", fontSize: 11 }}>{e.error_message}</div>}
        </div>
      ))}
    </div>
  );
}

function BindingsTab({ agents }: { agents: BoundAgent[] }) {
  if (agents.length === 0) {
    return <div style={{ color: "#64748b", fontSize: 13, padding: "20px 0" }}>暂无 Agent 绑定到此 Provider</div>;
  }
  return (
    <div>
      {agents.map((a) => (
        <div key={a.role_id} style={{
          background: "#1e293b", borderRadius: 8, padding: "10px 16px",
          marginBottom: 6, border: "1px solid #334155",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div>
            <span style={{ fontWeight: 600, color: "#f1f5f9", fontSize: 13 }}>{a.display_name}</span>
            <span style={{ fontSize: 10, color: "#94a3b8", marginLeft: 8 }}>{a.role_key}</span>
          </div>
          <div style={{ fontSize: 11, textAlign: "right" }}>
            <div style={{ color: "#e2e8f0" }}>{a.model_name || "—"}</div>
            <div style={{ color: a.is_locked ? "#f59e0b" : "#6366f1" }}>
              {a.binding_mode === "locked" ? "锁定" : a.binding_mode === "manual_with_fallback" ? "手动+后备" : "自动"}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
