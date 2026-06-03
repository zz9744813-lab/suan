import { useEffect, useRef, useState } from "react";
import {
  listProviders, createProvider, updateProvider, deleteProvider, testProvider,
  healthCheckProvider, previewProviderModels,
  listRoles, setRole,
} from "../api";
import type {
  ModelProvider, ModelRoleAssignment, ModelProviderTestResult,
  ModelHealthCheckResult, ModelHealthCheckItem, ModelHealthStatus,
  ModelHealthItemName, ModelHealthItemStatus,
} from "../types";

// P0-MODEL-3: status → label/colour mapping for the health pill.
// Colours come from the existing design tokens (--state-ok / --state-warn
// / --state-error) so the pill blends in with the rest of the app.
const HEALTH_BADGE: Record<ModelHealthStatus, { label: string; cls: string }> = {
  healthy:        { label: "健康",  cls: "ok" },
  degraded:       { label: "部分通过", cls: "warn" },
  unreachable:    { label: "无法连接", cls: "error" },
  auth_failed:    { label: "鉴权失败", cls: "error" },
  model_missing:  { label: "模型不存在", cls: "error" },
  unknown_error:  { label: "未知错误", cls: "error" },
};

// P15 / P0-HEALTH-1: per-test badge mapping. Same colour tokens as
// HEALTH_BADGE so the per-test list reads the same as the top-level
// pill.
const TEST_BADGE: Record<ModelHealthItemStatus, { label: string; cls: string }> = {
  passed:  { label: "通过", cls: "ok" },
  warning: { label: "偏慢", cls: "warn" },
  failed:  { label: "失败", cls: "error" },
  skipped: { label: "跳过", cls: "muted" },
};

// P15 / P0-HEALTH-1: how each test name is shown in the UI.
const TEST_LABEL: Record<ModelHealthItemName, string> = {
  short_chat:    "Ping / 短对话",
  json_output:   "JSON 严格输出",
  critic_schema: "Critic Schema 跟随",
  long_text:     "长文本 (≥ 1000 字)",
};

// P15 / P0-HEALTH-1: per-role health warnings. When the operator
// binds a model to a role that requires a test the model FAILED, the
// role matrix shows a red warning so they notice before the next
// pipeline run.
function roleRisk(rr: Record<string, string> | undefined, role: string): {
  state: "suitable" | "risky" | "unsuitable" | "unknown";
  reason: string;
} {
  const v = rr?.[role] ?? "unknown";
  if (v === "suitable") return { state: "suitable", reason: "" };
  if (v === "unknown") return { state: "unknown", reason: "未跑健康检查" };
  if (v.startsWith("unsuitable")) return { state: "unsuitable", reason: v };
  if (v.startsWith("risky")) return { state: "risky", reason: v };
  return { state: "unknown", reason: v };
}

// Role names follow the agent roles wired into the pipeline. Order is
// the on-screen order; the backend has no canonical order.
const ROLES: Array<{ key: string; defaultTemp: number; defaultTokens: number; group: "core" | "writing" | "memory" }> = [
  { key: "Chief",        defaultTemp: 0.6, defaultTokens: 2000, group: "core" },
  { key: "Planner",      defaultTemp: 0.7, defaultTokens: 2000, group: "core" },
  { key: "Draft",        defaultTemp: 0.9, defaultTokens: 6000, group: "writing" },
  { key: "Critic",       defaultTemp: 0.0, defaultTokens: 3500, group: "writing" },
  { key: "Rewrite",      defaultTemp: 0.7, defaultTokens: 6000, group: "writing" },
  { key: "Continuity",   defaultTemp: 0.3, defaultTokens: 2000, group: "writing" },
  { key: "MemoryUpdate", defaultTemp: 0.3, defaultTokens: 2000, group: "memory" },
  { key: "Learning",     defaultTemp: 0.4, defaultTokens: 1500, group: "memory" },
];

// P0-MODEL-2: each provider is a card. The form is now split into
// the persistent form (name / base_url / default_model / enabled / extra)
// and a "replace key" affordance (P0-MODEL-5) so editing other
// fields never sends the real key over the wire.

type EditState =
  | { mode: "create"; draft: Partial<ModelProvider> }
  | { mode: "edit";   id: number; draft: Partial<ModelProvider>; replacingKey: boolean };

export function ModelsPage() {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [roles, setRoles] = useState<ModelRoleAssignment[]>([]);
  const [editing, setEditing] = useState<EditState | null>(null);
  const [testResult, setTestResult] = useState<{ providerId: number; result: ModelProviderTestResult } | null>(null);
  // P0-MODEL-3: per-provider health probe result. Distinct from
  // ``testResult`` so the two panes don't fight for the same UI slot.
  const [healthResult, setHealthResult] = useState<{ providerId: number; result: ModelHealthCheckResult } | null>(null);
  // P0-MODEL-6: small inline success message for the create/edit flow.
  // Without it, a successful create looked like "I clicked save and
  // nothing happened" because the form just closed and the new card
  // appeared at the bottom of a long list. Auto-clears after 3s.
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  // P0-MODEL-7: track the in-flight "拉取模型" call so the button
  // shows a spinner / "拉取中…" label and can't be double-fired.
  // Lives in the form's own state rather than on the row because
  // the row doesn't exist yet on the create flow.
  const [previewBusy, setPreviewBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // P15 / P0-HEALTH-1 fix: ``healthResult?.providerId === p.id`` is
  // FALSE while the request is in flight (state is null until the
  // promise resolves), which means the 健康检查 button showed no
  // loading state and wasn't disabled — combined with the backend's
  // 600s read timeout and no frontend fetch timeout, a stuck request
  // made the page look like a black screen. We track the in-flight
  // provider id separately so the button can react immediately.
  const [healthBusy, setHealthBusy] = useState<number | null>(null);
  // Same fix for 「测试连接」: a single busy flag is global and races
  // with the 编辑 / 删除 / 启用 buttons. Use a per-action busy set
  // for the test call so other actions stay responsive.
  const [testBusy, setTestBusy] = useState<number | null>(null);

  const refresh = () => {
    listProviders().then(setProviders).catch(() => {});
    listRoles().then(setRoles).catch(() => {});
  };
  useEffect(refresh, []);

  // P0-MODEL-10: when the user clicks 「编辑」, the form used to
  // render at the bottom of the page (after the role-binding matrix)
  // and the user couldn't see it without scrolling. We now:
  //   1) render the form in a fixed-position right-side drawer so
  //      it's always in the viewport
  //   2) highlight the Provider card being edited with the
  //      ``.editing`` class so it's obvious which row owns the drawer
  //   3) scroll the card into view on entry (defensive — the drawer
  //      is fixed so this only matters on tiny viewports)
  //   4) close on Escape, click-on-backdrop, or the existing 取消
  //      button. We also trap focus to the drawer while it's open
  //      so Tab doesn't escape into the page behind.
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const drawerRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!editing) return;
    // Scroll the source card into view. setTimeout 0 lets React paint
    // the ``.editing`` highlight first so the user sees it animate
    // to the centre. Only matters in edit mode — create mode has no
    // source card to scroll to.
    if (editing.mode !== "edit") return;
    const id = editing.id;
    if (id == null) return;
    const t = setTimeout(() => {
      cardRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);
    return () => clearTimeout(t);
  }, [editing?.mode, editing?.mode === "edit" ? editing.id : null]);
  useEffect(() => {
    if (!editing) return;
    // ESC to close. Keep the handler on the document so the user
    // doesn't have to focus the drawer first.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setEditing(null);
      }
    };
    document.addEventListener("keydown", onKey);
    // Auto-focus the first input in the drawer so the user can
    // start typing immediately.
    const t = setTimeout(() => {
      const firstInput = drawerRef.current?.querySelector<HTMLInputElement>(
        "input, select, textarea, button",
      );
      firstInput?.focus();
    }, 50);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(t);
    };
  }, [editing]);

  // P0-MODEL-7: stateless model-list preview. Two paths:
  //   1) ``create`` mode — the row hasn't been saved yet, so we hit
  //      the new ``/preview-models`` endpoint with the form's
  //      base_url + api_key.
  //   2) ``edit`` mode — the row already has a real key on the
  //      server, but the browser only sees the masked preview
  //      (P0-6). Use the existing ``/test`` endpoint (which uses
  //      the saved key) so the user can refresh the dropdown
  //      without re-pasting the full key.
  const onPreviewModels = async () => {
    if (!editing) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    const baseUrl = (editing.draft.base_url ?? "").trim();
    if (!baseUrl) {
      setErrorMsg("请先填写 Base URL。");
      return;
    }
    setPreviewBusy(true);
    try {
      let models: string[] = [];
      let message = "";
      if (editing.mode === "create") {
        const apiKey = (editing.draft.api_key ?? "").trim();
        if (!baseUrl.startsWith("mock://") && !apiKey) {
          setErrorMsg("拉取模型前请先填写 API Key。");
          setPreviewBusy(false);
          return;
        }
        const r = await previewProviderModels(baseUrl, apiKey);
        if (!r.ok) {
          const msg = r.message || "拉取失败";
          const sug = r.suggestion ? `（${r.suggestion}）` : "";
          setErrorMsg(`${msg}${sug}`);
          return;
        }
        models = r.models ?? [];
        message = r.message || `✓ 拉取到 ${models.length} 个模型。`;
      } else {
        // edit mode — reuse the saved key
        const r = await testProvider(editing.id);
        if (!r.ok) {
          setErrorMsg(r.message || "拉取失败");
          if (r.suggestion) setErrorMsg((prev) => `${prev}（${r.suggestion}）`);
          return;
        }
        models = r.models ?? [];
        message = r.message || `✓ 拉取到 ${models.length} 个模型。`;
      }
      if (models.length === 0) {
        setErrorMsg("该 Provider 没有返回任何模型。请检查 Base URL 是否正确，或该服务是否提供 /v1/models。");
        return;
      }
      setEditing({
        ...editing,
        draft: { ...editing.draft, model_list: models },
      });
      // If the user hasn't picked a default_model yet, default to
      // the first one so the dropdown has a sensible initial
      // selection. Don't clobber an existing choice.
      if (!editing.draft.default_model && models[0]) {
        setEditing((prev) =>
          prev
            ? { ...prev, draft: { ...prev.draft, default_model: models[0], model_list: models } }
            : prev,
        );
      }
      setSuccessMsg(`✓ ${message}已填入下拉框。`);
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const onSave = async () => {
    if (!editing) return;
    setBusy(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      if (editing.mode === "create") {
        // Create always requires a real key. The save button's
        // ``disabled`` rule also gates on this, but defend in depth
        // because the user can submit via Enter from any field.
        if (!editing.draft.api_key) {
          setErrorMsg("新建 Provider 必须填写 API Key。");
          setBusy(false);
          return;
        }
        await createProvider(editing.draft);
        setSuccessMsg(`✓ Provider「${editing.draft.name}」已创建。`);
        setTimeout(() => setSuccessMsg(null), 3000);
      } else {
        // Edit: if the user didn't open the "replace key" panel, we
        // strip the empty key from the payload so the backend keeps
        // the existing one. If they did open it and typed something,
        // we send that through.
        const payload: Partial<ModelProvider> = { ...editing.draft };
        if (!editing.replacingKey || !payload.api_key) {
          delete payload.api_key;
        }
        await updateProvider(editing.id, payload);
        setSuccessMsg(`✓ Provider「${editing.draft.name}」已保存。`);
        setTimeout(() => setSuccessMsg(null), 3000);
      }
      setEditing(null);
      refresh();
    } catch (e: any) {
      // P0-MODEL-6: surface the backend's pydantic 422 field list when
      // available, otherwise fall back to the generic Error message.
      // ``e.details`` comes from the unified APIError envelope.
      const details = e?.details as Record<string, string> | undefined;
      const statusLine = e?.status ? `HTTP ${e.status}` : "";
      if (details && Object.keys(details).length > 0) {
        const lines = Object.entries(details)
          .map((([k, v]) => `· ${k}: ${v}`))
          .join("\n");
        setErrorMsg([statusLine, e?.message ?? "保存失败", lines].filter(Boolean).join("\n"));
      } else if (e?.detail && Array.isArray(e.detail)) {
        // FastAPI validation 422 — show field-level reasons.
        const lines = (e.detail as any[])
          .map((d) => {
            const loc = Array.isArray(d?.loc) ? d.loc.filter((l: any) => l !== "body").join(".") : "?";
            return `· ${loc || "?"}: ${d?.msg ?? "校验失败"}`;
          })
          .join("\n");
        setErrorMsg([statusLine, e?.message ?? "保存失败", lines].filter(Boolean).join("\n"));
      } else {
        setErrorMsg([statusLine, e?.message ?? String(e)].filter(Boolean).join("\n"));
      }
    } finally {
      setBusy(false);
    }
  };

  const onTest = async (id: number) => {
    setTestBusy(id);
    setErrorMsg(null);
    try {
      const r = await testProvider(id);
      setTestResult({ providerId: id, result: r });
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setTestBusy(null);
    }
  };

  // P0-MODEL-3: ping a specific model (or default) with a 4-token
  // call. The endpoint is slower than a UI-side ping, so we set a
  // per-provider ``healthBusy`` flag so the button text + disabled
  // state update immediately (and stay correct if the request
  // hangs). Without this the button stayed clickable and looked
  // dead — see P15 / P0-HEALTH-1 fix notes above.
  const onHealthCheck = async (p: ModelProvider, model?: string) => {
    setErrorMsg(null);
    setHealthBusy(p.id);
    try {
      const r = await healthCheckProvider(p.id, model);
      setHealthResult({ providerId: p.id, result: r });
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setHealthBusy(null);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm("确认删除这个 Provider？所有角色绑定将失效。")) return;
    await deleteProvider(id);
    refresh();
  };

  const onSetRole = async (
    role: string,
    providerId: number,
    model: string,
    temperature: number,
    maxTokens: number,
  ) => {
    if (!providerId || !model) return;
    try {
      await setRole(role, {
        provider_id: providerId,
        model,
        temperature,
        max_tokens: maxTokens,
      });
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    }
  };

  const onToggleEnabled = async (p: ModelProvider) => {
    try {
      const payload: Partial<ModelProvider> = { ...p, enabled: !p.enabled };
      // Don't send the (masked) key on a status-only toggle.
      delete (payload as any).api_key;
      delete (payload as any).has_api_key;
      await updateProvider(p.id, payload);
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    }
  };

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>模型配置</h1>
          <div className="sub">
            所有 Agent 共享 OpenAI 兼容协议。Base URL 以 <code>mock://</code> 开头时启用本地占位 LLM。
            API Key 永远不会完整回显到浏览器（仅显示前缀/后缀掩码）。
          </div>
        </div>
        <div className="actions">
          <button
            className="primary"
            onClick={() => setEditing({
              mode: "create",
              draft: { name: "", base_url: "https://api.openai.com/v1", api_key: "", default_model: "", enabled: true },
            })}
          >
            + 新建 Provider
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="card error-card" role="alert">
          <div className="row">
            <b>操作失败</b>
            <span className="spacer" />
            <button onClick={() => setErrorMsg(null)}>关闭</button>
          </div>
          <pre className="error-pre">{errorMsg}</pre>
        </div>
      )}

      {successMsg && (
        <div className="card success-card" role="status">
          <div className="row">
            <b>{successMsg}</b>
            <span className="spacer" />
            <button onClick={() => setSuccessMsg(null)}>关闭</button>
          </div>
        </div>
      )}

      {/* P0-MODEL-2: provider cards (one per provider) */}
      <div className="provider-grid">
        {providers.length === 0 && (
          <div className="card muted">还没有 Provider。点击右上角「+ 新建 Provider」开始。</div>
        )}
        {providers.map((p) => {
          const isTesting = testResult?.providerId === p.id;
          const isHealthChecking = healthResult?.providerId === p.id;
          const health = p.last_health_status
            ? HEALTH_BADGE[p.last_health_status as ModelHealthStatus] ?? HEALTH_BADGE.unknown_error
            : null;
          return (
            <div
              key={p.id}
              ref={(el) => { cardRefs.current[p.id] = el; }}
              className={`provider-card ${p.enabled ? "" : "disabled"} ${editing?.mode === "edit" && editing.id === p.id ? "editing" : ""}`}
            >
              <div className="provider-card-head">
                <div className="row" style={{ gap: 10 }}>
                  <div className="provider-card-name">{p.name}</div>
                  {p.enabled
                    ? <span className="pill succeeded tiny">启用</span>
                    : <span className="pill stopped tiny">禁用</span>}
                  {/* P0-MODEL-3: small status pill on the header. */}
                  {health && (
                    <span
                      className={`pill tiny ${health.cls}`}
                      title={p.last_health_message || ""}
                    >
                      {health.label}
                    </span>
                  )}
                </div>
                <button
                  className="link small"
                  onClick={() => onToggleEnabled(p)}
                  title={p.enabled ? "禁用该 Provider" : "启用该 Provider"}
                >
                  {p.enabled ? "禁用" : "启用"}
                </button>
              </div>
              <div className="provider-card-body">
                <div className="kv">
                  <span className="k">Base URL</span>
                  <span className="v mono small ellipsis" title={p.base_url}>{p.base_url}</span>
                </div>
                <div className="kv">
                  <span className="k">API Key</span>
                  <span className="v mono small">
                    {p.has_api_key
                      ? <><span className="gold">{p.api_key}</span> <span className="muted">（已配置，完整 Key 不返回浏览器）</span></>
                      : <span className="muted">未配置</span>}
                  </span>
                </div>
                <div className="kv">
                  <span className="k">默认模型</span>
                  <span className="v mono small">
                    {p.default_model || <span className="muted">—</span>}
                    {p.model_list.length > 0 && p.default_model && !p.model_list.includes(p.default_model) && (
                      <span className="warn tiny" style={{ marginLeft: 6 }} title="默认模型不在该 Provider 的模型列表中">
                        不在列表
                      </span>
                    )}
                  </span>
                </div>
                <div className="kv">
                  <span className="k">模型数</span>
                  <span className="v mono small">{p.model_list.length || "—"}</span>
                </div>
                <div className="kv">
                  <span className="k">最近测试</span>
                  <span className="v small">
                    {p.last_test_status
                      ? <span className={p.last_test_status === "ok" ? "ok" : "error"}>{p.last_test_status}</span>
                      : <span className="muted">—</span>}
                    {p.last_test_message && <span className="muted tiny" style={{ marginLeft: 6 }}>· {p.last_test_message}</span>}
                    {p.last_test_at && <span className="muted tiny" style={{ marginLeft: 6 }}>· {new Date(p.last_test_at).toLocaleString()}</span>}
                  </span>
                </div>
                {/* P0-MODEL-3: per-model health row. */}
                <div className="kv">
                  <span className="k">健康</span>
                  <span className="v small">
                    {p.last_health_at
                      ? <>
                          <span className={health?.cls ?? "muted"}>
                            {health?.label ?? p.last_health_status ?? "—"}
                          </span>
                          {p.last_health_model && (
                            <span className="mono tiny muted" style={{ marginLeft: 6 }}>
                              {p.last_health_model}
                            </span>
                          )}
                          {p.last_health_latency_ms != null && (
                            <span className="muted tiny" style={{ marginLeft: 6 }}>
                              · {p.last_health_latency_ms}ms
                            </span>
                          )}
                          <span className="muted tiny" style={{ marginLeft: 6 }}>
                            · {new Date(p.last_health_at).toLocaleString()}
                          </span>
                        </>
                      : <span className="muted">— 还没跑过</span>}
                  </span>
                </div>
                {p.extra && Object.keys(p.extra).length > 0 && (
                  <div className="kv">
                    <span className="k">Extra</span>
                    <span className="v mono tiny">
                      {Object.entries(p.extra).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}
                    </span>
                  </div>
                )}
              </div>
              <div className="provider-card-foot">
                <button
                  onClick={() => onTest(p.id)}
                  disabled={testBusy === p.id || !p.enabled}
                  title={p.enabled ? "测试 Provider 连接并拉取模型列表" : "Provider 已禁用"}
                >
                  {testBusy === p.id ? "测试中…" : "测试连接"}
                </button>
                {/* P0-MODEL-3: per-model health probe button. */}
                <button
                  onClick={() => onHealthCheck(p)}
                  disabled={healthBusy === p.id || !p.enabled}
                  title={p.enabled ? `向 ${p.default_model || "默认模型"} 发送一次 ping` : "Provider 已禁用"}
                >
                  {healthBusy === p.id ? "检查中…" : "健康检查"}
                </button>
                <button onClick={() => setEditing({ mode: "edit", id: p.id, draft: { ...p }, replacingKey: false })}>
                  编辑
                </button>
                <button className="danger" onClick={() => onDelete(p.id)}>删除</button>
              </div>
              {isTesting && testResult && (
                <div className="provider-card-test">
                  <div className={testResult.result.ok ? "ok" : "error"}>
                    {testResult.result.ok ? "✓" : "✗"} {testResult.result.message}
                  </div>
                  {testResult.result.suggestion && (
                    <div className="warn small" style={{ marginTop: 4 }}>建议：{testResult.result.suggestion}</div>
                  )}
                  {testResult.result.models.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div className="muted tiny" style={{ marginBottom: 4 }}>识别到 {testResult.result.models.length} 个模型：</div>
                      <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                        {testResult.result.models.map((m) => <span key={m} className="pill tiny">{m}</span>)}
                      </div>
                    </div>
                  )}
                  <div className="muted tiny" style={{ marginTop: 8 }}>延迟：{testResult.result.latency_ms}ms</div>
                </div>
              )}
              {/* P15 / P0-HEALTH-1: health-check result pane. Shows the
                  aggregate pill + the 4 individual tests + role
                  recommendations. ``results`` is always an array
                  (the new backend contract) so the map is safe even
                  if the array is empty (e.g. model_missing). */}
              {isHealthChecking && healthResult && (
                <div className="provider-card-test">
                  <div className="row" style={{ alignItems: "center", gap: 8 }}>
                    <span className={healthResult.result.ok ? "ok" : "error"} style={{ fontSize: 14 }}>
                      {healthResult.result.ok ? "✓" : "✗"}
                    </span>
                    <b>{HEALTH_BADGE[healthResult.result.status]?.label ?? healthResult.result.status}</b>
                    <span className="muted small">· 评分 {healthResult.result.score}/100</span>
                    <span className="spacer" />
                    <span className="muted tiny">
                      模型 {healthResult.result.model} · 累计 {healthResult.result.latency_ms}ms
                    </span>
                  </div>
                  <div className="small" style={{ marginTop: 4 }}>
                    {healthResult.result.message}
                  </div>
                  {healthResult.result.suggestion && (
                    <div className="warn small" style={{ marginTop: 4 }}>建议：{healthResult.result.suggestion}</div>
                  )}

                  {healthResult.result.results.length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div className="muted tiny" style={{ marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                        分项测试 ({healthResult.result.results.length})
                      </div>
                      <div style={{ display: "grid", gap: 4 }}>
                        {healthResult.result.results.map((it) => {
                          const badge = TEST_BADGE[it.status];
                          return (
                            <div
                              key={it.name}
                              style={{
                                display: "grid",
                                gridTemplateColumns: "100px 56px 1fr",
                                gap: 8,
                                alignItems: "baseline",
                                fontSize: 12,
                                padding: "3px 6px",
                                background: "var(--bg-paper-soft)",
                                borderRadius: 4,
                              }}
                              title={it.raw_preview ?? it.message}
                            >
                              <span className="mono tiny">{TEST_LABEL[it.name]}</span>
                              <span className={`pill tiny ${badge.cls}`} style={{ justifySelf: "start" }}>
                                {badge.label}
                              </span>
                              <span className={badge.cls} style={{ fontSize: 12 }}>
                                {it.message}
                                {it.latency_ms > 0 && (
                                  <span className="muted tiny" style={{ marginLeft: 6 }}>· {it.latency_ms}ms</span>
                                )}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {Object.keys(healthResult.result.recommended_roles).length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div className="muted tiny" style={{ marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                        角色适配
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {Object.entries(healthResult.result.recommended_roles).map(([role, verdict]) => {
                          const risk = roleRisk(healthResult.result.recommended_roles, role);
                          const cls =
                            risk.state === "suitable"  ? "succeeded" :
                            risk.state === "risky"     ? "paused" :
                            risk.state === "unsuitable" ? "error" :
                                                          "stopped";
                          return (
                            <span
                              key={role}
                              className={`pill tiny ${cls}`}
                              title={verdict}
                            >
                              {role}: {risk.state === "suitable" ? "✓" : risk.state === "risky" ? "!" : risk.state === "unsuitable" ? "✗" : "?"}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="muted tiny" style={{ marginTop: 8 }}>
                    {new Date(healthResult.result.checked_at).toLocaleString()}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* P0-MODEL-4: role binding matrix */}
      <div className="card">
        <h3>角色绑定矩阵</h3>
        <p className="muted small">
          每个 Agent 角色使用哪个 Provider 的哪个模型、温度、max_tokens。
          角色没有显式绑定时，会回退到第一个启用的 Provider 的默认模型。
          修改后 Worker 下一次调用立即生效，无需重启。
        </p>
        <table className="role-matrix">
          <thead>
            <tr>
              <th>角色</th>
              <th>Provider</th>
              <th>模型</th>
              <th>温度</th>
              <th>Max Tokens</th>
              <th>健康</th>
            </tr>
          </thead>
          <tbody>
            {ROLES.map((meta) => {
              const current = roles.find((r) => r.role === meta.key);
              const provider = providers.find((p) => p.id === current?.provider_id);
              const temp = current?.temperature ?? meta.defaultTemp;
              const tokens = current?.max_tokens ?? meta.defaultTokens;
              return (
                <tr key={meta.key}>
                  <td>
                    <b>{meta.key}</b>
                    <div className="muted tiny">
                      {meta.group === "core" && "调度 / 规划"}
                      {meta.group === "writing" && "写作 / 评审"}
                      {meta.group === "memory" && "记忆 / 学习"}
                    </div>
                  </td>
                  <td>
                    <select
                      value={current?.provider_id ?? ""}
                      onChange={(e) => {
                        const pid = Number(e.target.value);
                        const prov = providers.find((p) => p.id === pid);
                        if (prov) onSetRole(meta.key, pid, current?.model ?? prov.default_model, temp, tokens);
                      }}
                    >
                      <option value="">— 未绑定 —</option>
                      {providers.filter((p) => p.enabled).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </td>
                  <td>
                    {provider && provider.model_list.length > 0 ? (
                      <select
                        value={current?.model ?? provider.default_model}
                        onChange={(e) => onSetRole(meta.key, provider.id, e.target.value, temp, tokens)}
                      >
                        {provider.model_list.map((m) => <option key={m} value={m}>{m}</option>)}
                      </select>
                    ) : (
                      <input
                        placeholder="模型名"
                        defaultValue={current?.model ?? ""}
                        onBlur={(e) => {
                          const v = e.target.value.trim();
                          if (v && current) onSetRole(meta.key, current.provider_id, v, temp, tokens);
                        }}
                      />
                    )}
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      defaultValue={temp.toFixed(1)}
                      style={{ width: 64 }}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (current && !Number.isNaN(v) && v !== temp) {
                          onSetRole(meta.key, current.provider_id, current.model, v, tokens);
                        }
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="100"
                      min="100"
                      defaultValue={tokens}
                      style={{ width: 80 }}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (current && !Number.isNaN(v) && v !== tokens) {
                          onSetRole(meta.key, current.provider_id, current.model, temp, v);
                        }
                      }}
                    />
                  </td>
                  <td>
                    {provider ? (
                      (() => {
                        // P15 / P0-HEALTH-1: prefer the rich per-test
                        // data over the older ping-only status. We
                        // also surface a per-role risk pill so the
                        // operator notices when Critic is bound to a
                        // model that failed critic_schema.
                        const recommended = provider.last_health_full?.recommended_roles ?? {};
                        const risk = roleRisk(recommended, meta.key);
                        const baseStatus = provider.last_health_status;
                        const latency = provider.last_health_latency_ms;
                        const baseBadge = baseStatus ? HEALTH_BADGE[baseStatus] : null;
                        if (!baseBadge) {
                          return <span className="muted tiny" title="还没跑过健康检查">待检查</span>;
                        }
                        return (
                          <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "flex-start" }}>
                            <span
                              className={`tiny ${baseBadge.cls}`}
                              title={provider.last_health_message ?? ""}
                            >
                              {baseBadge.label}
                              {latency != null && ` · ${latency}ms`}
                            </span>
                            {risk.state === "unsuitable" && (
                              <span
                                className="pill error tiny"
                                title={risk.reason}
                                style={{ cursor: "help" }}
                              >
                                ✗ {meta.key} 不适配
                              </span>
                            )}
                            {risk.state === "risky" && (
                              <span
                                className="pill paused tiny"
                                title={risk.reason}
                                style={{ cursor: "help" }}
                              >
                                ! {meta.key} 有风险
                              </span>
                            )}
                            {risk.state === "unknown" && (
                              <span
                                className="muted tiny"
                                title="最近一次健康检查的推荐结果未覆盖该角色；点击「健康检查」刷新。"
                              >
                                ? {meta.key} 未知
                              </span>
                            )}
                          </div>
                        );
                      })()
                    ) : (
                      <span className="muted tiny">未绑定</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* P0-MODEL-10: edit / create form used to render inline at the
          bottom of the page (after the role-binding matrix) so the
          user couldn't see it without scrolling. Now it lives in a
          fixed-position right-side drawer with a backdrop. Click the
          backdrop, the close ✕, the 取消 button, or press Escape to
          close. The Provider card being edited gets a ``.editing``
          highlight so it's obvious which row owns the drawer. */}
      {editing && (
        <div
          className="drawer-backdrop"
          onClick={() => setEditing(null)}
          role="presentation"
        >
          <div
            className="drawer"
            ref={drawerRef}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={editing.mode === "create" ? "新建 Provider" : `编辑 Provider：${editing.draft.name ?? ""}`}
          >
            <div className="card drawer-card">
              <div className="drawer-head">
                <h3 style={{ margin: 0 }}>{editing.mode === "create" ? "新建 Provider" : `编辑 Provider：${editing.draft.name ?? ""}`}</h3>
                <button
                  className="drawer-close"
                  onClick={() => setEditing(null)}
                  aria-label="关闭"
                  title="关闭 (Esc)"
                >
                  ✕
                </button>
              </div>
          <div className="grid-2">
            <div>
              <label>名称</label>
              <input
                value={editing.draft.name ?? ""}
                onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, name: e.target.value } })}
              />
            </div>
            <div>
              <label>默认模型</label>
              {editing.draft.model_list && editing.draft.model_list.length > 0 ? (
                // P0-MODEL-7: when the user has run 「拉取模型」 we
                // have a definitive list of what the provider
                // exposes. Render a dropdown so they can't typo a
                // model id the provider doesn't actually serve.
                <select
                  value={editing.draft.default_model ?? ""}
                  onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, default_model: e.target.value } })}
                >
                  <option value="">— 暂不设置 —</option>
                  {editing.draft.model_list.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  value={editing.draft.default_model ?? ""}
                  onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, default_model: e.target.value } })}
                  placeholder="gpt-4o-mini（或点下方「拉取模型」自动填充）"
                />
              )}
            </div>
          </div>
          {/* P0-MODEL-7: Base URL + 「拉取模型」 button. Clicking
              calls the new stateless preview endpoint and, on
              success, populates the default_model dropdown above. */}
          <label>Base URL（mock:// 开头走本地占位 LLM）</label>
          <div className="row" style={{ gap: 8 }}>
            <input
              value={editing.draft.base_url ?? ""}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, base_url: e.target.value } })}
              style={{ flex: 1 }}
            />
            <button
              type="button"
              onClick={onPreviewModels}
              disabled={
                previewBusy ||
                !editing.draft.base_url ||
                (!editing.draft.base_url.startsWith("mock://") &&
                  editing.mode === "create" &&
                  !editing.draft.api_key)
              }
              title={
                !editing.draft.base_url
                  ? "先填 Base URL"
                  : (!editing.draft.base_url.startsWith("mock://") &&
                      editing.mode === "create" &&
                      !editing.draft.api_key)
                    ? "非 mock:// URL 需要先填 API Key"
                    : "向该 Base URL 拉取可用模型列表"
              }
            >
              {previewBusy ? "拉取中…" : "🔄 拉取模型"}
            </button>
          </div>
          <label className="row" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={editing.draft.enabled ?? true}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, enabled: e.target.checked } })}
              style={{ width: "auto" }}
            />
            <span style={{ marginLeft: 6 }}>启用</span>
          </label>

          {/* P0-MODEL-5: API Key 安全编辑 */}
          {editing.mode === "create" ? (
            <>
              <label>API Key（必填）</label>
              <input
                type="password"
                // P0-MODEL-6: autoFocus the API key field on the create
                // form so the cursor lands in the most important
                // (and only non-defaulted) field after the user
                // clicks "+ 新建 Provider".
                autoFocus
                value={editing.draft.api_key ?? ""}
                onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, api_key: e.target.value } })}
                placeholder="sk-..."
              />
            </>
          ) : (
            <div className="key-edit-block">
              <label>API Key</label>
              <div className="row" style={{ gap: 10 }}>
                <span className="mono small">
                  {editing.draft.has_api_key
                    ? <>已配置：<span className="gold">{editing.draft.api_key}</span>（完整 Key 不返回浏览器）</>
                    : <span className="muted">未配置</span>}
                </span>
                <span className="spacer" />
                {!editing.replacingKey ? (
                  <button onClick={() => setEditing({ ...editing, replacingKey: true, draft: { ...editing.draft, api_key: "" } })}>
                    替换 Key
                  </button>
                ) : (
                  <>
                    <input
                      type="password"
                      autoFocus
                      placeholder="输入新的 API Key"
                      value={editing.draft.api_key ?? ""}
                      onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, api_key: e.target.value } })}
                      style={{ flex: 1, maxWidth: 360 }}
                    />
                    <button onClick={() => setEditing({ ...editing, replacingKey: false, draft: { ...editing.draft, api_key: editing.draft.api_key } })}>
                      取消替换
                    </button>
                  </>
                )}
              </div>
              <div className="muted tiny" style={{ marginTop: 4 }}>
                提示：保存时不点「替换 Key」就提交，会保留旧 Key 不变。
              </div>
            </div>
          )}

          <div className="row" style={{ marginTop: 4, alignItems: "center" }}>
            <label style={{ margin: 0 }}>Extra (JSON, 可选)</label>
            <span className="spacer" />
            {/* P0-MODEL-11: one-click accelerator for reasoning
                models. Most step-3 / o1 / deepseek-r1 / qwen3-thinking
                providers accept ``extra_body.reasoning_effort`` to
                skip the planning preamble. The backend already
                auto-injects it for known reasoning model names, but
                clicking this lets the user force it on for a model
                the heuristic doesn't recognise yet. */}
            <button
              type="button"
              className="tiny"
              onClick={() => {
                const v = JSON.stringify(
                  { inject_reasoning_effort: true, reasoning_effort: "low" },
                  null,
                  2,
                );
                setEditing({
                  ...editing,
                  draft: {
                    ...editing.draft,
                    extra: { inject_reasoning_effort: true, reasoning_effort: "low" },
                  },
                });
                // Also write it into the controlled textarea via
                // the DOM so the user sees the value immediately.
                const editingId = editing.mode === "edit" ? editing.id : "new";
                const ta = document.getElementById(
                  `extra-json-${editingId}`,
                ) as HTMLTextAreaElement | null;
                if (ta) ta.value = v;
              }}
              title="为推理模型（step-3 / o1 / deepseek-r1 / qwen3-thinking）注入 reasoning_effort=low，跳过内部思考，5-10x 加速"
            >
              ⚡ 一键加速（推理模型）
            </button>
          </div>
          <textarea
            id={`extra-json-${editing.mode === "edit" ? editing.id : "new"}`}
            rows={3}
            placeholder='{"inject_reasoning_effort": true, "reasoning_effort": "low"}  ← 推理模型可填这个提速 5-10x'
            defaultValue={editing.draft.extra ? JSON.stringify(editing.draft.extra, null, 2) : ""}
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (!v) {
                setEditing({ ...editing, draft: { ...editing.draft, extra: null } });
                return;
              }
              try {
                const parsed = JSON.parse(v);
                setEditing({ ...editing, draft: { ...editing.draft, extra: parsed } });
              } catch {
                // ignore — user can fix later
              }
            }}
          />

          <div className="row" style={{ marginTop: 12 }}>
            <span className="spacer" />
            <button onClick={() => setEditing(null)}>取消</button>
            <button
              className="primary"
              onClick={onSave}
              // P0-MODEL-6: gate the create button on api_key too.
              // Previously the disabled rule only checked ``name`` and
              // ``base_url`` — but the API key is also required for
              // create, so users could click "保存", get a generic
              // error toast, and think the whole flow was broken.
              disabled={
                busy ||
                !editing.draft.name ||
                !editing.draft.base_url ||
                (editing.mode === "create" && !editing.draft.api_key)
              }
            >
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
