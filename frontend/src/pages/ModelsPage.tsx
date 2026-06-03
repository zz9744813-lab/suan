import { useEffect, useState } from "react";
import {
  listProviders, createProvider, updateProvider, deleteProvider, testProvider,
  healthCheckProvider,
  listRoles, setRole,
} from "../api";
import type {
  ModelProvider, ModelRoleAssignment, ModelProviderTestResult,
  ModelHealthCheckResult, ModelHealthStatus,
} from "../types";

// P0-MODEL-3: status → label/colour mapping for the health pill.
// Colours come from the existing design tokens (--state-ok / --state-warn
// / --state-error) so the pill blends in with the rest of the app.
const HEALTH_BADGE: Record<ModelHealthStatus, { label: string; cls: string }> = {
  healthy:        { label: "健康",  cls: "ok" },
  degraded:       { label: "缓慢",  cls: "warn" },
  unreachable:    { label: "无法连接", cls: "error" },
  auth_failed:    { label: "鉴权失败", cls: "error" },
  model_missing:  { label: "模型不存在", cls: "error" },
  unknown_error:  { label: "未知错误", cls: "error" },
};

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
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const refresh = () => {
    listProviders().then(setProviders).catch(() => {});
    listRoles().then(setRoles).catch(() => {});
  };
  useEffect(refresh, []);

  const onSave = async () => {
    if (!editing) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      if (editing.mode === "create") {
        // Create always requires a real key.
        if (!editing.draft.api_key) {
          setErrorMsg("新建 Provider 必须填写 API Key。");
          return;
        }
        await createProvider(editing.draft);
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
      }
      setEditing(null);
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onTest = async (id: number) => {
    setBusy(true);
    try {
      const r = await testProvider(id);
      setTestResult({ providerId: id, result: r });
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  // P0-MODEL-3: ping a specific model (or default) with a 4-token
  // call. The endpoint is slower than a UI-side ping so we don't
  // bundle busy=true; we just disable the button inline.
  const onHealthCheck = async (p: ModelProvider, model?: string) => {
    setErrorMsg(null);
    try {
      const r = await healthCheckProvider(p.id, model);
      setHealthResult({ providerId: p.id, result: r });
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
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
            <div key={p.id} className={`provider-card ${p.enabled ? "" : "disabled"}`}>
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
                <button onClick={() => onTest(p.id)} disabled={busy}>测试连接</button>
                {/* P0-MODEL-3: per-model health probe button. */}
                <button
                  onClick={() => onHealthCheck(p)}
                  disabled={isHealthChecking || !p.enabled}
                  title={p.enabled ? `向 ${p.default_model || "默认模型"} 发送一次 ping` : "Provider 已禁用"}
                >
                  {isHealthChecking ? "检查中…" : "健康检查"}
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
              {/* P0-MODEL-3: health-check result pane. */}
              {isHealthChecking && healthResult && (
                <div className="provider-card-test">
                  <div className={healthResult.result.ok ? "ok" : "error"}>
                    {healthResult.result.ok ? "✓" : "✗"}{" "}
                    <b>{HEALTH_BADGE[healthResult.result.status]?.label ?? healthResult.result.status}</b>
                    {" "}— {healthResult.result.message}
                  </div>
                  {healthResult.result.suggestion && (
                    <div className="warn small" style={{ marginTop: 4 }}>建议：{healthResult.result.suggestion}</div>
                  )}
                  <div className="muted tiny" style={{ marginTop: 8 }}>
                    模型 {healthResult.result.model} · 延迟 {healthResult.result.latency_ms}ms ·{" "}
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
                      // P0-MODEL-3: prefer the per-model health probe
                      // over the older /test status because it actually
                      // exercises the model the role is bound to.
                      provider.last_health_status === "healthy"
                        ? <span className="ok tiny" title={provider.last_health_message ?? ""}>
                            良好 · {provider.last_health_latency_ms}ms
                          </span>
                        : provider.last_health_status === "degraded"
                        ? <span className="warn tiny" title={provider.last_health_message ?? ""}>
                            缓慢 · {provider.last_health_latency_ms}ms
                          </span>
                        : provider.last_health_status
                        ? <span className="error tiny" title={provider.last_health_message ?? ""}>
                            {HEALTH_BADGE[provider.last_health_status as ModelHealthStatus]?.label ?? provider.last_health_status}
                          </span>
                        : <span className="muted tiny" title="还没跑过健康检查">待检查</span>
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

      {editing && (
        <div className="card">
          <h3>{editing.mode === "create" ? "新建 Provider" : `编辑 Provider：${editing.draft.name ?? ""}`}</h3>
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
              <input
                value={editing.draft.default_model ?? ""}
                onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, default_model: e.target.value } })}
                placeholder="gpt-4o-mini"
              />
            </div>
          </div>
          <label>Base URL（mock:// 开头走本地占位 LLM）</label>
          <input
            value={editing.draft.base_url ?? ""}
            onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, base_url: e.target.value } })}
          />
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

          <label>Extra (JSON, 可选)</label>
          <textarea
            rows={3}
            placeholder='{"inject_reasoning_effort": true, "reasoning_effort": "low"}'
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
              disabled={busy || !editing.draft.name || !editing.draft.base_url}
            >
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
