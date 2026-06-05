import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { createProvider, getAgentRoleMatrix, testProvider } from "../api";
import type { AgentRoleMatrixItem, AgentRoleMatrixResponse, ModelProvider } from "../types";
import { AgentRoleEditorModal } from "../components/models";

interface ProviderSummary {
  id: number;
  name: string;
  base_url: string;
  enabled: boolean;
  default_model: string;
  model_count: number;
  healthy_count: number;
  failing_count: number;
  success_rate: number;
  avg_latency_ms: number | null;
  circuit_state: string;
  is_stub: boolean;
}

interface AgentSummary {
  role_id: number;
  role_key: string;
  display_name: string;
  category: string;
  enabled: boolean;
  binding_mode: string;
  provider_name: string | null;
  current_model: string | null;
  is_locked: boolean;
  allow_fallback: boolean;
  recent_status: string;
}

interface OverviewData {
  provider_count: number;
  enabled_provider_count: number;
  model_count: number;
  healthy_model_count: number;
  failing_model_count: number;
  mock_binding_count: number;
  locked_agent_count: number;
  auto_agent_count: number;
  providers: ProviderSummary[];
  agents: AgentSummary[];
}

type ProviderForm = {
  name: string;
  base_url: string;
  api_key: string;
  default_model: string;
};

const CATEGORY_LABELS: Record<string, string> = {
  writing: "写作",
  study: "拆书",
  memory: "记忆",
  discussion: "讨论",
  review: "评审",
  custom: "自定义",
};

const MODE_LABELS: Record<string, string> = {
  auto: "自动",
  manual: "手动",
  manual_with_fallback: "手动+备用",
  locked: "锁定",
};

const RECENT_STATUS_LABELS: Record<string, string> = {
  idle: "待命",
  queued: "排队",
  running: "运行中",
  waiting: "等待",
  succeeded: "完成",
  failed: "失败",
  disabled: "禁用",
};

export default function ModelConfigPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewData | null>(null);
  const [matrix, setMatrix] = useState<AgentRoleMatrixResponse | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<AgentRoleMatrixItem | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [providerForm, setProviderForm] = useState<ProviderForm>({
    name: "OpenRouter",
    base_url: "https://openrouter.ai/api/v1",
    api_key: "",
    default_model: "",
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const fetchOverview = async () => {
    setError("");
    try {
      const [overview, roleMatrix] = await Promise.all([
        api.get<OverviewData>("/api/model-control/overview"),
        getAgentRoleMatrix(),
      ]);
      setData(overview);
      setMatrix(roleMatrix);
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  const matrixByRoleId = useMemo(() => {
    const map = new Map<number, AgentRoleMatrixItem>();
    for (const item of matrix?.items ?? []) map.set(item.role.id, item);
    return map;
  }, [matrix]);

  const addProvider = async () => {
    if (!providerForm.name.trim()) {
      setError("Provider 名称不能为空");
      return;
    }
    if (!providerForm.base_url.trim()) {
      setError("Base URL 不能为空");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const provider = await createProvider({
        name: providerForm.name.trim(),
        base_url: providerForm.base_url.trim(),
        api_key: providerForm.api_key.trim(),
        default_model: providerForm.default_model.trim(),
        enabled: true,
      } as Partial<ModelProvider>);
      let pulledCount: number | null = null;
      if (providerForm.api_key.trim() || providerForm.base_url.trim().startsWith("mock://")) {
        const testResult = await testProvider(provider.id);
        if (testResult.ok) {
          pulledCount = testResult.models.length;
        } else {
          setError(testResult.suggestion ? `${testResult.message}；${testResult.suggestion}` : testResult.message);
        }
      }
      setAddOpen(false);
      setNotice(pulledCount == null ? `已添加 ${provider.name}` : `已添加 ${provider.name}，已拉取 ${pulledCount} 个模型`);
      await fetchOverview();
      navigate(`/models/providers/${provider.id}`);
    } catch (e: any) {
      setError(e?.message || "添加失败");
    } finally {
      setBusy(false);
    }
  };

  const probeAll = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.post("/api/model-control/probe-all", {}, 120_000);
      setNotice("健康检查已完成");
      await fetchOverview();
    } catch (e: any) {
      setError(e?.message || "健康检查失败");
    } finally {
      setBusy(false);
    }
  };

  const openAgent = (agent: AgentSummary) => {
    const item = matrixByRoleId.get(agent.role_id);
    if (item) setSelectedAgent(item);
  };

  if (loading) return <div style={{ padding: 24 }} className="muted">加载中...</div>;
  if (!data) return null;

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1180, margin: "0 auto" }}>
      <div className="page-header" style={{ marginBottom: 18 }}>
        <div>
          <h1>模型配置</h1>
          <div className="sub">健康状态摘要</div>
        </div>
        <div className="actions">
          <button className="ghost" onClick={fetchOverview} disabled={busy}>刷新</button>
          <button className="ghost" onClick={probeAll} disabled={busy}>
            {busy ? "检查中..." : "全量健康检查"}
          </button>
          <button className="primary" onClick={() => setAddOpen(true)} disabled={busy}>
            添加 API Provider
          </button>
        </div>
      </div>

      {error && (
        <div className="card dense" style={{ marginBottom: 12, borderColor: "rgba(238,77,90,0.35)", color: "var(--state-error)" }}>
          {error}
        </div>
      )}
      {notice && (
        <div className="card dense" style={{ marginBottom: 12, borderColor: "rgba(32,180,134,0.35)", color: "var(--state-ok)" }}>
          {notice}
        </div>
      )}

      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(6, minmax(120px, 1fr))" }}>
        <StatBox label="Provider" value={`${data.enabled_provider_count}/${data.provider_count}`} />
        <StatBox label="可用模型" value={String(data.healthy_model_count)} sub={`共 ${data.model_count}`} />
        <StatBox label="异常模型" value={String(data.failing_model_count)} warn={data.failing_model_count > 0} />
        <StatBox label="Mock 绑定" value={String(data.mock_binding_count)} warn={data.mock_binding_count > 0} />
        <StatBox label="锁定 Agent" value={String(data.locked_agent_count)} />
        <StatBox label="自动调度" value={String(data.auto_agent_count)} />
      </div>

      <Section title="Provider">
        {data.providers.length === 0 && <EmptyHint>暂无 Provider</EmptyHint>}
        {data.providers.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            onOpen={() => navigate(`/models/providers/${provider.id}`)}
          />
        ))}
      </Section>

      <Section title="Agent 状态">
        {data.agents.length === 0 && <EmptyHint>暂无 Agent</EmptyHint>}
        <div style={{ display: "grid", gap: 8 }}>
          {data.agents.map((agent) => (
            <AgentRow
              key={agent.role_id}
              agent={agent}
              editable={matrixByRoleId.has(agent.role_id)}
              onOpen={() => openAgent(agent)}
            />
          ))}
        </div>
      </Section>

      {addOpen && (
        <AddProviderModal
          form={providerForm}
          setForm={setProviderForm}
          busy={busy}
          onClose={() => setAddOpen(false)}
          onSave={addProvider}
        />
      )}

      {selectedAgent && (
        <AgentRoleEditorModal
          open={true}
          role={selectedAgent.role}
          binding={selectedAgent.binding}
          promptBinding={selectedAgent.prompt_binding}
          onClose={() => setSelectedAgent(null)}
          onSaved={() => {
            setSelectedAgent(null);
            setNotice("Agent 绑定已保存");
            fetchOverview();
          }}
        />
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  sub,
  warn,
}: {
  label: string;
  value: string;
  sub?: string;
  warn?: boolean;
}) {
  return (
    <div className="stat" style={{ borderColor: warn ? "rgba(238,77,90,0.35)" : undefined }}>
      <div className="label">{label}</div>
      <div className="num" style={{ color: warn ? "var(--state-error)" : undefined }}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 12px", color: "var(--text-secondary)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function EmptyHint({ children }: { children: string }) {
  return <div className="card dense muted">{children}</div>;
}

function ProviderCard({
  provider,
  onOpen,
}: {
  provider: ProviderSummary;
  onOpen: () => void;
}) {
  const success = Math.round((provider.success_rate ?? 0) * 100);
  const successColor =
    success >= 90 ? "var(--state-ok)" : success >= 60 ? "var(--state-warn)" : "var(--state-error)";

  return (
    <button
      onClick={onOpen}
      className="card dense"
      style={{
        width: "100%",
        display: "grid",
        gridTemplateColumns: "minmax(180px, 1fr) repeat(5, minmax(86px, auto)) 96px",
        alignItems: "center",
        gap: 12,
        marginBottom: 8,
        textAlign: "left",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <strong style={{ color: "var(--text-primary)" }}>{provider.name}</strong>
          <span className={`pill ${provider.enabled ? "succeeded" : "idle"}`}>
            {provider.enabled ? "启用" : "禁用"}
          </span>
          {provider.is_stub && <span className="pill paused">mock</span>}
        </div>
        <div className="muted tiny" style={{ marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {provider.base_url}
        </div>
      </div>
      <Metric label="模型" value={String(provider.model_count)} />
      <Metric label="可用" value={String(provider.healthy_count)} ok />
      <Metric label="失败" value={String(provider.failing_count)} warn={provider.failing_count > 0} />
      <Metric label="成功率" value={`${success}%`} color={successColor} />
      <Metric label="延迟" value={provider.avg_latency_ms != null ? `${provider.avg_latency_ms}ms` : "-"} />
      <div style={{ textAlign: "right", color: "var(--accent-gold)", fontSize: 12 }}>进入详情</div>
    </button>
  );
}

function Metric({
  label,
  value,
  ok,
  warn,
  color,
}: {
  label: string;
  value: string;
  ok?: boolean;
  warn?: boolean;
  color?: string;
}) {
  return (
    <div style={{ minWidth: 72 }}>
      <div className="muted tiny">{label}</div>
      <div style={{
        fontWeight: 700,
        color: color ?? (ok ? "var(--state-ok)" : warn ? "var(--state-error)" : "var(--text-primary)"),
      }}>
        {value}
      </div>
    </div>
  );
}

function AgentRow({
  agent,
  editable,
  onOpen,
}: {
  agent: AgentSummary;
  editable: boolean;
  onOpen: () => void;
}) {
  const modeColor =
    agent.binding_mode === "locked"
      ? "var(--state-warn)"
      : agent.binding_mode === "manual_with_fallback"
        ? "var(--accent-gold)"
        : "var(--state-ok)";

  return (
    <button
      className="card dense"
      onClick={onOpen}
      disabled={!editable}
      style={{
        width: "100%",
        display: "grid",
        gridTemplateColumns: "minmax(160px, 1.1fr) 126px minmax(180px, 1fr) 110px 86px",
        alignItems: "center",
        gap: 12,
        textAlign: "left",
      }}
    >
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <strong style={{ color: "var(--text-primary)" }}>{agent.display_name}</strong>
          {!agent.enabled && <span className="pill idle">禁用</span>}
        </div>
        <div className="muted tiny">{CATEGORY_LABELS[agent.category] || agent.category}</div>
      </div>
      <div>
        <div className="muted tiny">绑定模式</div>
        <div style={{ color: modeColor, fontWeight: 700 }}>
          {MODE_LABELS[agent.binding_mode] || agent.binding_mode}
        </div>
      </div>
      <div>
        <div className="muted tiny">当前模型</div>
        <div style={{ color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {agent.provider_name ? `${agent.provider_name} / ${agent.current_model || "-"}` : "未绑定"}
        </div>
      </div>
      <div>
        <div className="muted tiny">Fallback</div>
        <div style={{ color: agent.allow_fallback ? "var(--state-ok)" : "var(--state-warn)" }}>
          {agent.allow_fallback ? "允许" : "禁用"}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="muted tiny">最近状态</div>
        <div style={{ color: "var(--text-primary)" }}>
          {RECENT_STATUS_LABELS[agent.recent_status] || agent.recent_status}
        </div>
      </div>
    </button>
  );
}

function AddProviderModal({
  form,
  setForm,
  busy,
  onClose,
  onSave,
}: {
  form: ProviderForm;
  setForm: (next: ProviderForm) => void;
  busy: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  const patch = (body: Partial<ProviderForm>) => setForm({ ...form, ...body });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 520, maxWidth: "94vw" }}>
        <div className="modal-head">
          <h3>添加 API Provider</h3>
          <button className="modal-close" onClick={onClose}>&#10005;</button>
        </div>
        <div className="modal-body" style={{ display: "grid", gap: 12 }}>
          <label>
            <span className="muted small">Provider</span>
            <input className="input" value={form.name} onChange={(e) => patch({ name: e.target.value })} />
          </label>
          <label>
            <span className="muted small">Base URL</span>
            <input className="input" value={form.base_url} onChange={(e) => patch({ base_url: e.target.value })} />
          </label>
          <label>
            <span className="muted small">API Key</span>
            <input
              className="input"
              type="password"
              value={form.api_key}
              onChange={(e) => patch({ api_key: e.target.value })}
              placeholder="sk-..."
            />
          </label>
          <label>
            <span className="muted small">默认模型</span>
            <input
              className="input"
              value={form.default_model}
              onChange={(e) => patch({ default_model: e.target.value })}
              placeholder="可稍后在详情中设置"
            />
          </label>
        </div>
        <div className="modal-foot">
          <button onClick={onClose} disabled={busy}>取消</button>
          <button className="primary" onClick={onSave} disabled={busy}>
            {busy ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
