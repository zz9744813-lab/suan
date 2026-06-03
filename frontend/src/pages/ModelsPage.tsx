import { useEffect, useState } from "react";
import {
  listProviders, createProvider, updateProvider, deleteProvider, testProvider,
  listRoles, setRole,
} from "../api";
import type { ModelProvider, ModelRoleAssignment, ModelProviderTestResult } from "../types";

const ROLES = ["Chief", "Planner", "Draft", "Critic", "Rewrite", "Continuity", "MemoryUpdate", "Learning"];

export function ModelsPage() {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [roles, setRoles] = useState<ModelRoleAssignment[]>([]);
  const [editing, setEditing] = useState<Partial<ModelProvider> | null>(null);
  const [testResult, setTestResult] = useState<ModelProviderTestResult | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    listProviders().then(setProviders).catch(() => {});
    listRoles().then(setRoles).catch(() => {});
  };
  useEffect(refresh, []);

  const onSave = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      if (editing.id) await updateProvider(editing.id, editing);
      else await createProvider(editing);
      setEditing(null);
      refresh();
    } catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  };

  const onTest = async (id: number) => {
    setBusy(true);
    try {
      const r = await testProvider(id);
      setTestResult(r);
      refresh();
    } catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  };

  const onDelete = async (id: number) => {
    if (!confirm("确认删除这个 Provider？所有角色绑定将失效。")) return;
    await deleteProvider(id);
    refresh();
  };

  const onSetRole = async (role: string, providerId: number, model: string) => {
    if (!providerId || !model) return;
    try {
      await setRole(role, { provider_id: providerId, model });
      refresh();
    } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>模型配置</h1>
          <div className="sub">所有 Agent 共享 OpenAI 兼容协议。Base URL 以 <code>mock://</code> 开头时启用本地占位 LLM（无网络）。</div>
        </div>
        <div className="actions">
          <button className="primary" onClick={() => setEditing({
            name: "", base_url: "https://api.openai.com/v1", api_key: "",
            default_model: "", enabled: true, model_list: [],
          })}>+ 新建 Provider</button>
        </div>
      </div>

      <div className="card">
        <h3>Providers</h3>
        {providers.length === 0 ? (
          <div className="muted">还没有 Provider。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th><th>Base URL</th><th>默认模型</th>
                <th>模型列表</th><th>状态</th>
                <th>最近测试</th><th></th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id}>
                  <td>
                    <b>{p.name}</b>
                    {p.api_key && <div className="muted tiny mono">key: {p.api_key.slice(0, 4)}…{p.api_key.slice(-4)}</div>}
                  </td>
                  <td className="mono small">{p.base_url}</td>
                  <td className="mono">{p.default_model || <span className="muted">—</span>}</td>
                  <td className="muted small">
                    {p.model_list.length === 0 ? "—" : p.model_list.slice(0, 3).join(", ") + (p.model_list.length > 3 ? ` +${p.model_list.length - 3}` : "")}
                  </td>
                  <td>{p.enabled ? <span className="pill succeeded">启用</span> : <span className="pill stopped">禁用</span>}</td>
                  <td className="muted small">
                    {p.last_test_status
                      ? <span className={p.last_test_status === "ok" ? "ok" : "error"}>{p.last_test_status}</span>
                      : "—"}
                    {p.last_test_message && <div className="tiny ellipsis" style={{ maxWidth: 160 }}>{p.last_test_message}</div>}
                  </td>
                  <td>
                    <button onClick={() => onTest(p.id)} disabled={busy}>测试</button>
                    <button onClick={() => setEditing(p)} style={{ marginLeft: 4 }}>编辑</button>
                    <button className="danger" onClick={() => onDelete(p.id)} style={{ marginLeft: 4 }}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {testResult && (
        <div className="card">
          <h3>测试结果</h3>
          <div className={testResult.ok ? "ok" : "error"}>{testResult.ok ? "✓" : "✗"} {testResult.message}</div>
          {testResult.suggestion && <div className="warn small" style={{ marginTop: 4 }}>建议：{testResult.suggestion}</div>}
          {testResult.models.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="muted tiny" style={{ marginBottom: 4 }}>识别到 {testResult.models.length} 个模型：</div>
              <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                {testResult.models.map((m) => <span key={m} className="pill">{m}</span>)}
              </div>
            </div>
          )}
          <div className="muted tiny" style={{ marginTop: 8 }}>延迟：{testResult.latency_ms}ms</div>
          <div className="row" style={{ marginTop: 8 }}><span className="spacer" /><button onClick={() => setTestResult(null)}>关闭</button></div>
        </div>
      )}

      <div className="card">
        <h3>角色绑定</h3>
        <p className="muted small">每个 Agent 角色使用哪个 Provider 的哪个模型。当角色没有显式绑定时，会回退到第一个启用的 Provider 的默认模型。</p>
        {roles.length === 0 ? (
          <div className="muted">还没有绑定。直接在下方下拉框里挑一个 Provider 即可保存。</div>
        ) : (
          <table>
            <thead>
              <tr><th>角色</th><th>Provider</th><th>模型</th><th>温度</th><th>最大 Tokens</th></tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr key={r.id}>
                  <td><b>{r.role}</b></td>
                  <td className="mono">{r.provider_name ?? `#${r.provider_id}`}</td>
                  <td className="mono">{r.model}</td>
                  <td className="mono">{r.temperature.toFixed(1)}</td>
                  <td className="mono">{r.max_tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3 style={{ marginTop: 20 }}>快速绑定</h3>
        <div className="grid-2">
          {ROLES.map((role) => {
            const current = roles.find((r) => r.role === role);
            return (
              <div key={role} className="row gap-2" style={{ alignItems: "center" }}>
                <span style={{ width: 110 }} className="mono">{role}</span>
                <select
                  value={current?.provider_id ?? ""}
                  onChange={(e) => {
                    const pid = Number(e.target.value);
                    const prov = providers.find((p) => p.id === pid);
                    if (prov) onSetRole(role, pid, current?.model ?? prov.default_model);
                  }}
                  style={{ flex: 1 }}
                >
                  <option value="">— 未绑定 —</option>
                  {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <input
                  style={{ flex: 1 }}
                  placeholder="模型名"
                  defaultValue={current?.model ?? ""}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v && current && v !== current.model) {
                      onSetRole(role, current.provider_id, v);
                    }
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {editing && (
        <div className="card">
          <h3>{editing.id ? "编辑 Provider" : "新建 Provider"}</h3>
          <div className="grid-2">
            <div>
              <label>名称</label>
              <input value={editing.name ?? ""} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </div>
            <div>
              <label>默认模型</label>
              <input value={editing.default_model ?? ""} onChange={(e) => setEditing({ ...editing, default_model: e.target.value })} placeholder="gpt-4o-mini" />
            </div>
          </div>
          <label>Base URL（mock:// 开头走本地占位 LLM）</label>
          <input value={editing.base_url ?? ""} onChange={(e) => setEditing({ ...editing, base_url: e.target.value })} />
          <label>API Key</label>
          <input type="password" value={editing.api_key ?? ""} onChange={(e) => setEditing({ ...editing, api_key: e.target.value })} />
          <label className="row" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={editing.enabled ?? true}
              onChange={(e) => setEditing({ ...editing, enabled: e.target.checked })}
              style={{ width: "auto" }}
            />
            <span style={{ marginLeft: 6 }}>启用</span>
          </label>
          <div className="row" style={{ marginTop: 12 }}>
            <span className="spacer" />
            <button onClick={() => setEditing(null)}>取消</button>
            <button className="primary" onClick={onSave} disabled={busy || !editing.name || !editing.base_url}>
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
