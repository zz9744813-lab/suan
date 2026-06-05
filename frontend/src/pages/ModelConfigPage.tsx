import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useNavigate } from "react-router-dom";

interface ProviderSummary {
  id: number; name: string; enabled: boolean;
  model_count: number; healthy_count: number; failing_count: number;
  success_rate: number; avg_latency_ms: number | null;
  circuit_state: string; is_stub: boolean;
}

interface AgentSummary {
  role_id: number; role_key: string; display_name: string;
  category: string; enabled: boolean;
  binding_mode: string; provider_name: string | null;
  current_model: string | null; is_locked: boolean;
  allow_fallback: boolean; recent_status: string;
}

interface OverviewData {
  provider_count: number; enabled_provider_count: number;
  model_count: number; healthy_model_count: number;
  failing_model_count: number; mock_binding_count: number;
  locked_agent_count: number; auto_agent_count: number;
  providers: ProviderSummary[];
  agents: AgentSummary[];
}

const CATEGORY_LABELS: Record<string, string> = {
  writing: "写作", study: "拆书", memory: "记忆",
  discussion: "讨论", custom: "自定义",
};

const MODE_LABELS: Record<string, string> = {
  auto: "自动", manual_with_fallback: "手动+后备", locked: "锁定",
};

export default function ModelConfigPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchOverview = async () => {
    try {
      const data = await api.get<OverviewData>("/api/model-control/overview");
      setData(data);
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOverview(); }, []);

  if (loading) return <div style={{ padding: 24, color: "#94a3b8" }}>加载中...</div>;
  if (error) return <div style={{ padding: 24, color: "#ef4444" }}>{error}</div>;
  if (!data) return null;

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 20 }}>模型配置</h1>

      {/* Stats bar */}
      <div style={{ display: "flex", gap: 16, marginBottom: 28, flexWrap: "wrap" }}>
        <StatBox label="Provider" value={`${data.enabled_provider_count}/${data.provider_count}`} />
        <StatBox label="可用模型" value={String(data.healthy_model_count)} sub={`共 ${data.model_count}`} />
        <StatBox label="异常模型" value={String(data.failing_model_count)} warn={data.failing_model_count > 0} />
        <StatBox label="Mock 绑定" value={String(data.mock_binding_count)} warn={data.mock_binding_count > 0} />
        <StatBox label="锁定 Agent" value={String(data.locked_agent_count)} />
        <StatBox label="自动调度" value={String(data.auto_agent_count)} />
      </div>

      {/* Provider list */}
      <Section title="Provider">
        {data.providers.length === 0 && <EmptyHint>暂无 Provider</EmptyHint>}
        {data.providers.map((p) => (
          <ProviderCard key={p.id} p={p} onClick={() => navigate(`/models/providers/${p.id}`)} />
        ))}
      </Section>

      {/* Agent status */}
      <Section title="Agent 状态">
        {data.agents.length === 0 && <EmptyHint>暂无 Agent</EmptyHint>}
        {data.agents.map((a) => (
          <AgentRow key={a.role_id} a={a} />
        ))}
      </Section>

      {/* Refresh */}
      <div style={{ marginTop: 20, textAlign: "center" }}>
        <button onClick={fetchOverview} style={{
          padding: "6px 18px", borderRadius: 6, border: "1px solid #334155",
          background: "#1e293b", color: "#e2e8f0", cursor: "pointer",
        }}>刷新</button>
      </div>
    </div>
  );
}

function StatBox({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div style={{
      background: "#1e293b", borderRadius: 8, padding: "12px 18px",
      border: warn ? "1px solid #b91c1c" : "1px solid #334155",
      minWidth: 110,
    }}>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: warn ? "#fca5a5" : "#f1f5f9" }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "#64748b" }}>{sub}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: "#94a3b8", marginBottom: 12 }}>{title}</h2>
      {children}
    </div>
  );
}

function EmptyHint({ children }: { children: string }) {
  return <div style={{ color: "#64748b", fontSize: 12, padding: "12px 0" }}>{children}</div>;
}

function ProviderCard({ p, onClick }: { p: ProviderSummary; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "#1e293b", borderRadius: 8, padding: "14px 18px",
        marginBottom: 8, cursor: "pointer", border: "1px solid #334155",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#6366f1")}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#334155")}
    >
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 600, color: "#f1f5f9" }}>{p.name}</span>
          {p.is_stub && <span style={{ fontSize: 10, color: "#f59e0b", background: "#422006", padding: "1px 6px", borderRadius: 4 }}>mock</span>}
          {!p.enabled && <span style={{ fontSize: 10, color: "#94a3b8", background: "#1e293b", padding: "1px 6px", borderRadius: 4, border: "1px solid #475569" }}>已禁用</span>}
        </div>
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
          模型 {p.model_count} · 可用 {p.healthy_count} · 失败 {p.failing_count}
          {p.avg_latency_ms != null ? ` · ${p.avg_latency_ms}ms` : ""}
          {" · "}{p.circuit_state === "open" ? "熔断" : p.circuit_state === "half_open" ? "半开" : "正常"}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: 18, fontWeight: 600, color: p.success_rate >= 0.9 ? "#22c55e" : p.success_rate >= 0.5 ? "#f59e0b" : "#ef4444" }}>
          {(p.success_rate * 100).toFixed(0)}%
        </div>
        <div style={{ fontSize: 10, color: "#64748b" }}>成功率</div>
        <div style={{ fontSize: 10, color: "#6366f1", marginTop: 4 }}>进入详情 →</div>
      </div>
    </div>
  );
}

function AgentRow({ a }: { a: AgentSummary }) {
  const mode = a.binding_mode || "auto";
  const modeColor = mode === "locked" ? "#f59e0b" : mode === "manual_with_fallback" ? "#6366f1" : "#22c55e";
  return (
    <div style={{
      background: "#1e293b", borderRadius: 8, padding: "10px 16px",
      marginBottom: 6, border: "1px solid #334155",
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontWeight: 600, color: "#f1f5f9", fontSize: 13 }}>{a.display_name}</span>
        <span style={{
          fontSize: 10, color: "#cbd5e1", background: "#1e293b",
          border: "1px solid #475569", padding: "1px 6px", borderRadius: 4,
        }}>{CATEGORY_LABELS[a.category] || a.category}</span>
        <span style={{ fontSize: 10, color: modeColor, background: modeColor + "18", padding: "1px 6px", borderRadius: 4 }}>
          {MODE_LABELS[mode] || mode}
        </span>
      </div>
      <div style={{ textAlign: "right", fontSize: 11 }}>
        <div style={{ color: "#e2e8f0" }}>
          {a.provider_name ? `${a.provider_name} / ${a.current_model || "—"}` : "未绑定"}
        </div>
        <div style={{ color: "#64748b" }}>
          {a.is_locked ? "Fallback: 禁用" : a.allow_fallback ? "Fallback: 允许" : "Fallback: 关闭"}
        </div>
      </div>
    </div>
  );
}
