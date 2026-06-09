import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import {
  createProvider,
  deleteProvider,
  getAgentRoleMatrix,
  getProviderDeletePreview,
  healthCheckProvider,
  testProvider,
} from "../api";
import type {
  AgentRoleMatrixItem,
  AgentRoleMatrixResponse,
  ModelProvider,
  ProviderDeletePreview,
} from "../types";
import { AgentRoleEditorModal, AutoConfigureModal, ConfirmDialog } from "../components/models";
import { DomainBreadcrumb } from "../components/layout/DomainBreadcrumb";
import { getWorkbenchDomain } from "../lib/domainMap";

interface ProviderSummary {
  id: number;
  name: string;
  base_url: string;
  enabled: boolean;
  default_model: string;
  // P-Auto-Config: AutoConfigureModal 用 ``model_list`` 做"轻量
  // 模型启发" (含 mini/flash/lite/small 关键字的). 后端
  // ``listProviders`` 返回的 provider 字典里通常有这字段, 但
  // ``ProviderSummary`` 是 ModelConfigPage 自己的窄类型, 所以
  // 这里显式补一个 optional 字段, 找不到时 modal 退化到
  // ``default_model`` 兜底.
  model_list?: string[];
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
  // P-Delete-Preview: which provider the delete dialog is open for,
  // plus the preflight summary we just fetched. ``null`` = dialog
  // closed. We keep them side by side so the dialog body shows
  // cascade effects without a second round-trip.
  const [deletePreview, setDeletePreview] = useState<{
    provider: ProviderSummary;
    preview: ProviderDeletePreview;
  } | null>(null);
  const [deletingProviderId, setDeletingProviderId] = useState<number | null>(null);
  // ① 一键自动配置: 弹 AutoConfigureModal 让用户为所有 auto
  // 模式 Agent 分配推荐模型. 选中的 provider 作为"种子 provider"
  // 传给 modal 展示, 但 modal 内部其实是调
  // ``autoConfigureAgents`` 全局配置.
  const [autoConfigureOpen, setAutoConfigureOpen] = useState(false);
  // ② Provider 单条健康检查: 每行右侧"健康检查"按钮触发
  // (而不是全量 probe-all). per-provider 的 busy 状态.
  const [probingProviderId, setProbingProviderId] = useState<number | null>(null);
  // 实时监测: 全局轮询定时器, 每 30s 拉一次 overview, 刷新
  // healthy_count / failing_count / success_rate. 启动/停止由
  // 状态 ``monitoringOn`` 控制, 默认开启.
  const [monitoringOn, setMonitoringOn] = useState(true);
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

  // P-Delete-Preview: open the confirmation dialog for ``provider``.
  // We fetch the preflight summary (cascade effects: role bindings
  // that will be deleted, call events that will lose their
  // provider_id) and only then mount the dialog. If the fetch
  // fails (404, network, ...) we surface the error in the page-
  // level error banner and bail — no dialog appears, no destructive
  // action taken.
  const onProviderDelete = async (provider: ProviderSummary) => {
    if (deletePreview?.provider.id === provider.id) {
      // Already showing the dialog for this provider.
      return;
    }
    try {
      const preview = await getProviderDeletePreview(provider.id);
      setDeletePreview({ provider, preview });
    } catch (e: any) {
      setError(`无法加载删除预检：${e?.message ?? e}`);
    }
  };
  // P-Delete-Preview: actual DELETE call. Called from the
  // ConfirmDialog's onConfirm handler. We track in-flight state
  // per provider so the inline delete button on the card shows
  // "删除中..." while we wait.
  const onProviderDeleteConfirm = async () => {
    if (!deletePreview) return;
    const { provider, preview } = deletePreview;
    setDeletingProviderId(provider.id);
    try {
      await deleteProvider(provider.id);
      setDeletePreview(null);
      const cascade = preview.will_cascade_role_bindings.length;
      if (cascade > 0) {
        setNotice(`已删除 Provider「${preview.provider_name}」及 ${cascade} 个角色绑定`);
      } else {
        setNotice(`已删除 Provider「${preview.provider_name}」`);
      }
      await fetchOverview();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setDeletingProviderId(null);
    }
  };
  const onProviderDeleteCancel = () => setDeletePreview(null);

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

  // ② 健康检查: 触发单个 Provider 的健康检查 (不阻塞其他行).
  // 端点 ``POST /api/models/providers/{id}/health-check`` 会跑一轮
  // 真实 HTTP 调用测试, 然后回写 ``model_providers`` 行的
  // healthy_count / failing_count / success_rate / avg_latency_ms /
  // last_health_at. 我们只需要 busy 状态 + 触发后 refetch overview.
  const probeOne = async (providerId: number) => {
    setProbingProviderId(providerId);
    setError("");
    try {
      await healthCheckProvider(providerId);
      setNotice(`Provider #${providerId} 健康检查已完成`);
      await fetchOverview();
    } catch (e: any) {
      setError(e?.message || `Provider #${providerId} 健康检查失败`);
    } finally {
      setProbingProviderId(null);
    }
  };

  // ③ 实时监测: 每 30s 拉一次 overview, 刷新 healthy_count /
  // failing_count / success_rate / last_health_at. 这不是真去
  // 跑健康检查, 而是让数据库里已有的"上次 health check 结果"
  // 反映到 UI. 后台要持续跑"真"健康检查可以接
  // ``ProviderHealthMonitor`` 服务, UI 这一层只是被动轮询.
  useEffect(() => {
    if (!monitoringOn) return;
    const id = window.setInterval(() => {
      fetchOverview().catch(() => {/* 静默, 不弹错 */});
    }, 30_000);
    return () => window.clearInterval(id);
  }, [monitoringOn]); // eslint-disable-line react-hooks/exhaustive-deps

  const openAgent = (agent: AgentSummary) => {
    const item = matrixByRoleId.get(agent.role_id);
    if (item) setSelectedAgent(item);
  };

  if (loading) return <div style={{ padding: 24 }} className="muted">加载中...</div>;
  if (!data) return null;

  const governanceDomain = getWorkbenchDomain("governance");

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1180, margin: "0 auto" }}>
      <div className="legacy-domain-breadcrumb">
        <DomainBreadcrumb current="治理 / 模型配置" links={governanceDomain.drilldowns} />
      </div>
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
          {/* ③ 实时监测开关: 30s 轮询 overview. 关闭则 UI 静态
              (只有用户手动刷新才更新), 适合排查/演示场景. */}
          <button
            className="ghost"
            onClick={() => setMonitoringOn((v) => !v)}
            title={monitoringOn ? "实时监测中（30s 轮询）" : "实时监测已暂停"}
            style={{
              color: monitoringOn ? "var(--state-ok)" : "var(--text-muted)",
              borderColor: monitoringOn ? "rgba(32,180,134,0.35)" : undefined,
            }}
          >
            {monitoringOn ? "● 实时监测" : "○ 实时监测"}
          </button>
          {/* ① 一键自动配置: 把矩阵里所有"自动"模式的 Agent
              按系统推荐分配最佳 Provider/Model, 详情见
              ``backend/app/routers/agent_roles.py::auto_configure_agents``. */}
          <button
            className="primary"
            onClick={() => setAutoConfigureOpen(true)}
            disabled={busy || data.providers.length === 0}
            title="为所有自动模式 Agent 分配推荐 Provider/Model"
          >
            一键自动配置
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
            onDelete={() => onProviderDelete(provider)}
            onProbe={() => probeOne(provider.id)}
            deleteBusy={deletingProviderId === provider.id}
            probeBusy={probingProviderId === provider.id}
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

      {/* ① 一键自动配置弹窗. 选中列表里第一个 provider 作为
          "展示用" provider, 但 modal 内部其实跑的是全局
          ``autoConfigureAgents``. 完成后会触发 refetch + 通知. */}
      <AutoConfigureModal
        open={autoConfigureOpen}
        // ``ModelProvider`` 包含 ``api_key``/``model_list`` 等宽
        // 字段; ProviderSummary 是窄类型, 不强转 ``as any`` 是因
        // 为 modal 内部只读 ``name / model_list / default_model``,
        // 这些字段 ProviderSummary 都有 (model_list 是 optional 但
        // 后端 overview 端点会回传).
        provider={(data.providers[0] as unknown as ModelProvider | undefined) ?? null}
        matrixItems={matrix?.items ?? []}
        onClose={() => setAutoConfigureOpen(false)}
        onConfigured={() => {
          setAutoConfigureOpen(false);
          setNotice("一键自动配置已完成");
          fetchOverview();
        }}
      />

      {/* P-Delete-Preview: 删除 Provider 二次确认弹窗.
          只在 ``deletePreview`` 不为 null 时挂载; 弹窗自己处理
          cancel/backdrop-click 来调用 onCancel 清空状态. */}
      {deletePreview && (
        <ConfirmDialog
          open={true}
          title="删除 Provider?"
          subtitle={
            <span>
              <b style={{ color: "var(--text-primary)" }}>
                {deletePreview.preview.provider_name}
              </b>
              <br />
              {deletePreview.preview.base_url}
            </span>
          }
          summary={deletePreview.preview.summary}
          details={
            deletePreview.preview.will_cascade_role_bindings.length > 0 ? (
              <div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    marginBottom: 6,
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  将被级联删除的角色绑定
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 18,
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}
                >
                  {deletePreview.preview.will_cascade_role_bindings.map((b) => (
                    <li key={b.id}>
                      <span style={{ fontFamily: "monospace" }}>{b.role}</span>
                      <span style={{ color: "var(--text-muted)" }}>
                        {" → "}
                        {b.model}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null
          }
          dangerLevel={deletePreview.preview.danger_level}
          confirmLabel="确认删除"
          cancelLabel="取消"
          confirmDisabled={deletingProviderId === deletePreview.provider.id}
          onCancel={onProviderDeleteCancel}
          onConfirm={onProviderDeleteConfirm}
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
  onDelete,
  onProbe,
  deleteBusy,
  probeBusy,
}: {
  provider: ProviderSummary;
  onOpen: () => void;
  // P-Delete-Preview: opens the delete confirmation dialog.
  // ``onDelete`` is responsible for the preflight fetch; the card
  // just surfaces the button + busy state. ``stopPropagation`` on
  // the click is essential — the card used to be a single ``<button>``
  // that navigated to the detail page on any click, and we now
  // have a sibling delete button inside the same row.
  onDelete: () => void;
  deleteBusy: boolean;
  // ② 健康检查: 只触发这一个 Provider 的健康检查 (不阻塞其他
  // 行), 端点是 ``POST /api/models/providers/{id}/health-check``.
  onProbe: () => void;
  probeBusy: boolean;
}) {
  const success = Math.round((provider.success_rate ?? 0) * 100);
  const successColor =
    success >= 90 ? "var(--state-ok)" : success >= 60 ? "var(--state-warn)" : "var(--state-error)";

  // P-Delete-Preview: the row used to be one giant ``<button>`` that
  // routed to the detail page no matter where you clicked. Split it
  // into a ``<div>`` shell with two explicit buttons so the new
  // delete button can call ``stopPropagation`` and not steal the
  // navigate-on-row-click behavior.
  return (
    <div
      className="card dense provider-card-row"
      data-provider-id={provider.id}
      style={{
        width: "100%",
        display: "grid",
        gridTemplateColumns: "minmax(180px, 1fr) repeat(5, minmax(86px, auto)) 180px",
        alignItems: "center",
        gap: 12,
        marginBottom: 8,
      }}
    >
      <button
        type="button"
        onClick={onOpen}
        title="进入详情"
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          textAlign: "left",
          cursor: "pointer",
          color: "inherit",
          font: "inherit",
          minWidth: 0,
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
      </button>
      <Metric label="模型" value={String(provider.model_count)} />
      <Metric label="可用" value={String(provider.healthy_count)} ok />
      <Metric label="失败" value={String(provider.failing_count)} warn={provider.failing_count > 0} />
      <Metric label="成功率" value={`${success}%`} color={successColor} />
      <Metric label="延迟" value={provider.avg_latency_ms != null ? `${provider.avg_latency_ms}ms` : "-"} />
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onProbe(); }}
          className="ghost"
          disabled={probeBusy}
          style={{ fontSize: 12, padding: "4px 10px" }}
          title="单独对这个 Provider 跑一次健康检查"
        >
          {probeBusy ? "检查中..." : "健康检查"}
        </button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onOpen(); }}
          className="ghost"
          style={{ fontSize: 12, padding: "4px 10px" }}
        >
          进入详情
        </button>
        {/* P-Delete-Preview: red "删除" button. ``stopPropagation`` so
            the row's outer click (now a no-op since the row is a
            ``<div>``, but kept for safety if the markup is ever
            wrapped in a clickable container again) doesn't fire. */}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="danger"
          disabled={deleteBusy}
          style={{ fontSize: 12, padding: "4px 10px" }}
        >
          {deleteBusy ? "删除中..." : "删除"}
        </button>
      </div>
    </div>
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
