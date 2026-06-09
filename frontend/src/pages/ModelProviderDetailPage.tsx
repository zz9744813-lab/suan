import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { testProvider } from "../api";

interface ProviderInfo {
  id: number; name: string; base_url: string;
  enabled: boolean; default_model: string;
  model_count: number; is_stub: boolean;
  // P-Monitor: 实时监测 banner 要展示的字段, 来自
  // ``/api/model-control/providers/{id}`` 后端聚合, 详情见
  // ``backend/app/routers/model_control.py``.
  healthy_count?: number; failing_count?: number;
  success_rate?: number | null; avg_latency_ms?: number | null;
  circuit_state?: string;
  last_health_at?: string | null;
  consecutive_successes?: number; consecutive_failures?: number;
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
  const [deletingModel, setDeletingModel] = useState<string | null>(null);
  const [togglingModel, setTogglingModel] = useState<string | null>(null);
  const [probeResults, setProbeResults] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  // P-Monitor: 详情页实时监测. 15s 拉一次 (详情页比列表页更需要
  // 接近实时, 因为这里展示的是单 Provider 的 health_score 时间
  // 轴, 越快越好). 切走 tab 不会停; 离开页面再清理.
  const [monitoringOn, setMonitoringOn] = useState(true);
  // P-Monitor: "重置熔断" 按钮的 in-flight 状态.
  const [resettingCircuit, setResettingCircuit] = useState(false);

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

  // P-Monitor: 15s 轮询. 静默失败 (不弹错), 避免在网络抖动时
  // 把 banner 推高亮闪.
  useEffect(() => {
    if (!monitoringOn) return;
    const id = window.setInterval(() => {
      fetchDetail().catch(() => {/* 静默 */});
    }, 15_000);
    return () => window.clearInterval(id);
  }, [monitoringOn, providerId]);

  // P-Monitor: 重置熔断. 端点 ``POST /api/models/providers/{id}/circuit/reset``
  // 会把 ``model_providers`` 行的 ``circuit_state`` 从 ``open`` /
  // ``half_open`` 拨回 ``closed``, 同时清零 consecutive_failures.
  const resetCircuit = async () => {
    if (!providerId) return;
    setResettingCircuit(true);
    setError("");
    try {
      await api.post(`/api/models/providers/${providerId}/circuit/reset`);
      setNotice("熔断器已重置");
      await fetchDetail();
    } catch (e: any) {
      setError(e?.message || "重置熔断失败");
    } finally {
      setResettingCircuit(false);
    }
  };

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

  const deleteModel = async (modelName: string) => {
    if (!data?.provider || !providerId) return;
    if (!confirm(`从「${data.provider.name}」移除模型「${modelName}」？\n\n这会隐藏该模型、禁用它的健康快照，并从 Provider 模型列表移除；不会删除远端供应商模型。`)) return;
    setDeletingModel(modelName);
    setError("");
    setNotice("");
    try {
      await api.delete(`/api/model-control/providers/${providerId}/models/${encodeURIComponent(modelName)}`);
      setData((prev) => prev ? {
        ...prev,
        provider: {
          ...prev.provider,
          model_count: Math.max(0, prev.provider.model_count - 1),
          default_model: prev.provider.default_model === modelName ? "" : prev.provider.default_model,
        },
        models: prev.models.filter((model) => model.model_name !== modelName),
        bound_agents: prev.bound_agents.filter((agent) => agent.model_name !== modelName),
      } : prev);
      setNotice(`已从模型列表移除 ${modelName}`);
      await fetchDetail();
    } catch (e: any) {
      setError(e?.message || "删除模型失败");
    } finally {
      setDeletingModel(null);
    }
  };

  const toggleModelDisabled = async (modelName: string, disabled: boolean) => {
    if (!providerId) return;
    const action = disabled ? "enable" : "disable";
    if (!disabled && !confirm(`禁用模型「${modelName}」？\n\n禁用后它会保留在列表里，但不会再被自动选模或 Agent 绑定使用。`)) return;
    setTogglingModel(modelName);
    setError("");
    setNotice("");
    try {
      await api.post(`/api/model-control/providers/${providerId}/models/${encodeURIComponent(modelName)}/${action}`);
      setNotice(disabled ? `已启用 ${modelName}` : `已禁用 ${modelName}`);
      await fetchDetail();
    } catch (e: any) {
      setError(e?.message || (disabled ? "启用模型失败" : "禁用模型失败"));
    } finally {
      setTogglingModel(null);
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

      {/* P-Monitor: 实时监测 banner. 显示 4 个核心指标:
            - 可用 / 失败 (来自 model_health_snapshots)
            - 24h 成功率 / 延迟 (来自 model_providers.success_rate_24h)
            - 熔断状态 (closed/half_open/open) — 打开时显示
              "重置熔断" 按钮.
            - 上次检查时间.
          整行根据 circuit_state 着色 (open = 红色脉冲边框,
          half_open = 黄色边框, closed = 默认). */}
      {data && (
        <MonitorBanner
          info={data.provider}
          modelCount={data.models.length}
          monitoringOn={monitoringOn}
          onToggleMonitoring={() => setMonitoringOn((v) => !v)}
          onResetCircuit={resetCircuit}
          resettingCircuit={resettingCircuit}
        />
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
        <ModelsTab
          models={data.models}
          probeOne={probeOne}
          probeResults={probeResults}
          deleteModel={deleteModel}
          deletingModel={deletingModel}
          toggleModelDisabled={toggleModelDisabled}
          togglingModel={togglingModel}
        />
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

/**
 * MonitorBanner — P-Monitor 实时监测 banner.
 *
 * 把 4 个核心 SRE 指标塞进一行, 让操作员一眼看清这个 Provider
 * 当前是健康 / 降级 / 熔断:
 *   - 可用 / 失败 (来自 ``model_health_snapshots`` 实时表)
 *   - 24h 成功率 (来自 ``model_providers.success_rate_24h``)
 *   - 平均延迟
 *   - 熔断状态 (closed / half_open / open)
 *
 * 整行边框颜色由 ``circuit_state`` 决定:
 *   - closed    → 默认 (灰)
 *   - half_open → 黄色, 提示"半开恢复中, 观察中"
 *   - open      → 红色, 提示"已熔断, 不再发请求"
 *
 * "重置熔断" 按钮只在 ``circuit_state != 'closed'`` 时显示.
 */
function MonitorBanner({
  info, modelCount, monitoringOn, onToggleMonitoring, onResetCircuit, resettingCircuit,
}: {
  info: ProviderInfo;
  modelCount: number;
  monitoringOn: boolean;
  onToggleMonitoring: () => void;
  onResetCircuit: () => void;
  resettingCircuit: boolean;
}) {
  const circuit = (info.circuit_state ?? "closed").toLowerCase();
  const circuitColor =
    circuit === "open" ? "#ef4444" :
    circuit === "half_open" ? "#f59e0b" :
    "#22c55e";
  const circuitLabel =
    circuit === "open" ? "熔断打开" :
    circuit === "half_open" ? "半开恢复" :
    "正常";
  const success = info.success_rate != null ? Math.round((info.success_rate ?? 0) * 100) : null;
  const lastAt = info.last_health_at
    ? new Date(info.last_health_at).toLocaleTimeString("zh-CN")
    : "—";

  return (
    <div
      style={{
        marginBottom: 16, padding: "10px 14px", borderRadius: 8,
        background: "rgba(30,41,59,0.6)",
        border: `1px solid ${circuitColor}55`,
        boxShadow: circuit === "open" ? `0 0 0 1px ${circuitColor}33` : "none",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        fontSize: 12,
      }}
    >
      {/* 监测开关 */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          aria-hidden
          style={{
            width: 8, height: 8, borderRadius: 4,
            background: monitoringOn ? "#22c55e" : "#64748b",
            boxShadow: monitoringOn ? "0 0 6px #22c55eaa" : "none",
            animation: monitoringOn ? "pulse 2s infinite" : "none",
          }}
        />
        <span style={{ color: monitoringOn ? "#22c55e" : "#94a3b8" }}>
          {monitoringOn ? "实时监测中 (15s)" : "监测已暂停"}
        </span>
        <button
          onClick={onToggleMonitoring}
          style={{
            marginLeft: 4, background: "none", border: "1px solid #334155",
            color: "#94a3b8", padding: "2px 8px", borderRadius: 4, cursor: "pointer",
            fontSize: 11,
          }}
        >
          {monitoringOn ? "暂停" : "开启"}
        </button>
      </div>

      <div style={{ height: 24, width: 1, background: "#334155" }} />

      <BannerStat label="可用" value={`${info.healthy_count ?? 0} / ${modelCount}`} color="#22c55e" />
      <BannerStat label="失败" value={`${info.failing_count ?? 0}`} color={info.failing_count ? "#ef4444" : "#64748b"} />
      <BannerStat label="24h 成功率" value={success != null ? `${success}%` : "—"} color={success == null ? "#94a3b8" : success >= 90 ? "#22c55e" : success >= 60 ? "#f59e0b" : "#ef4444"} />
      <BannerStat label="平均延迟" value={info.avg_latency_ms != null ? `${info.avg_latency_ms}ms` : "—"} />
      <BannerStat label="熔断" value={circuitLabel} color={circuitColor} pulse={circuit === "open"} />
      <BannerStat label="上次检查" value={lastAt} />

      {circuit !== "closed" && (
        <button
          onClick={onResetCircuit}
          disabled={resettingCircuit}
          style={{
            marginLeft: "auto",
            padding: "4px 12px", borderRadius: 4,
            border: `1px solid ${circuitColor}`,
            background: "transparent", color: circuitColor,
            cursor: resettingCircuit ? "not-allowed" : "pointer",
            fontSize: 12, opacity: resettingCircuit ? 0.6 : 1,
          }}
        >
          {resettingCircuit ? "重置中..." : "重置熔断"}
        </button>
      )}
    </div>
  );
}

function BannerStat({
  label, value, color, pulse,
}: {
  label: string; value: string; color?: string; pulse?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
      <span style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</span>
      <span
        style={{
          color: color ?? "#e2e8f0",
          fontSize: 14, fontWeight: 600,
          fontFamily: "monospace",
          animation: pulse ? "pulse 1.5s infinite" : "none",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function ModelsTab({
  models, probeOne, probeResults, deleteModel, deletingModel, toggleModelDisabled, togglingModel,
}: {
  models: ModelItem[];
  probeOne: (name: string) => void;
  probeResults: Record<string, string>;
  deleteModel: (name: string) => void;
  deletingModel: string | null;
  toggleModelDisabled: (name: string, disabled: boolean) => void;
  togglingModel: string | null;
}) {
  if (models.length === 0) {
    return <div style={{ color: "#64748b", fontSize: 13, padding: "20px 0" }}>暂无模型数据，请先「拉取模型列表」</div>;
  }
  return (
    <div>
      {models.map((m) => {
        const disabled = m.status === "disabled";
        return (
        <div key={m.model_name} style={{
          background: disabled ? "rgba(30,41,59,0.55)" : "#1e293b", borderRadius: 8, padding: "12px 16px",
          marginBottom: 8, border: disabled ? "1px solid rgba(148,163,184,0.35)" : "1px solid #334155",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          opacity: disabled ? 0.72 : 1,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontWeight: 600, color: "#f1f5f9", fontSize: 13 }}>{m.model_name}</span>
              <span style={{
                fontSize: 10, padding: "1px 6px", borderRadius: 4,
                color: disabled ? "#fbbf24" : (STATUS_COLORS[m.status] || "#94a3b8"),
                background: (disabled ? "#fbbf24" : (STATUS_COLORS[m.status] || "#94a3b8")) + "18",
              }}>
                {disabled ? "已禁用" : (STATUS_LABELS[m.status] || m.status)}
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
              disabled={disabled}
              style={{
                marginTop: 4, padding: "3px 10px", borderRadius: 4,
                border: "1px solid #475569", background: "#0f172a",
                color: "#e2e8f0", cursor: disabled ? "not-allowed" : "pointer", fontSize: 11,
              }}
            >测试</button>
            <button
              onClick={() => toggleModelDisabled(m.model_name, disabled)}
              disabled={togglingModel === m.model_name}
              style={{
                marginRight: 8, padding: "4px 10px", borderRadius: 4,
                border: disabled ? "1px solid #22c55e" : "1px solid #f59e0b",
                background: disabled ? "rgba(34,197,94,0.12)" : "rgba(245,158,11,0.12)",
                color: disabled ? "#86efac" : "#fbbf24",
                cursor: "pointer", fontSize: 12,
              }}
            >
              {togglingModel === m.model_name ? "处理中..." : disabled ? "启用" : "禁用"}
            </button>
            <button
              onClick={() => deleteModel(m.model_name)}
              disabled={deletingModel === m.model_name}
              title="从当前 Provider 模型列表移除"
              style={{
                marginTop: 4, marginLeft: 6, padding: "3px 10px", borderRadius: 4,
                border: "1px solid rgba(239,68,68,0.55)", background: "rgba(127,29,29,0.35)",
                color: "#fecaca", cursor: deletingModel === m.model_name ? "not-allowed" : "pointer", fontSize: 11,
              }}
            >{deletingModel === m.model_name ? "删除中..." : "删除"}</button>
            {probeResults[m.model_name] && (
              <div style={{ fontSize: 9, color: "#94a3b8", marginTop: 2 }}>{probeResults[m.model_name]}</div>
            )}
          </div>
        </div>
        );
      })}
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
