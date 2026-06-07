/**
 * ProviderAccordion — Provider 折叠摘要 (P4 §3)
 *
 * 默认折叠只显示摘要 (name / base url / 默认模型 / 模型数 / 启用 /
 * 健康). 展开后显示完整编辑区 (跟原 ModelsPage 的 provider 编辑
 * 逻辑一致, 但折叠态不再抢主视觉).
 */
import { useState } from "react";
import type { ModelProvider } from "../../types";

const PROVIDER_TYPE_URLS: Record<string, string> = {
  openrouter: "https://openrouter.ai/api/v1",
  deepseek: "https://api.deepseek.com/v1",
  openai: "https://api.openai.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  siliconflow: "https://api.siliconflow.cn/v1",
  custom: "",
};

export function ProviderAccordion({
  provider, defaultExpanded = false, onChange, onDelete, onTest, onHealth, onPreviewModels, busy,
}: {
  provider: ModelProvider;
  defaultExpanded?: boolean;
  onChange: (body: Partial<ModelProvider>) => Promise<void> | void;
  onDelete: () => void;
  onTest: () => void;
  onHealth: (model?: string) => void;
  onPreviewModels: (baseUrl: string, apiKey: string) => Promise<string[]> | void;
  busy: { test?: boolean; health?: boolean; preview?: boolean; delete?: boolean };
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [draft, setDraft] = useState<Partial<ModelProvider>>({});
  const [providerType, setProviderType] = useState<string>("custom");
  const [showApiKey, setShowApiKey] = useState(false);
  const [previewedModels, setPreviewedModels] = useState<string[] | null>(null);
  const healthColor = (() => {
    const s = provider.last_health_status;
    if (!s) return "gray";
    if (s === "healthy") return "green";
    if (s === "degraded") return "gold";
    if (s === "unreachable" || s === "auth_failed" || s === "model_missing" || s === "unknown_error") return "red";
    return "gray";
  })();

  // P0-MODEL-FAILOVER: circuit-breaker badge. Open = red stripe, half_open
  // = orange pulse, closed = green dot.
  const circuitBadge = (() => {
    const c = provider.circuit_state ?? "closed";
    if (c === "open") return { color: "red", text: "熔断中" };
    if (c === "half_open") return { color: "gold", text: "半开" };
    return { color: "green", text: "" };
  })();

  return (
    <div className={`provider-accordion ${expanded ? "expanded" : ""}`} data-health={healthColor}>
      <button className="provider-accordion-head" onClick={() => setExpanded((v) => !v)}>
        <span className="provider-accordion-caret">{expanded ? "▾" : "▸"}</span>
        <span className="provider-accordion-name">{provider.name}</span>
        <span className="provider-accordion-model">{provider.default_model}</span>
        <span className="provider-accordion-count">{provider.model_list?.length ?? 0} 模型</span>
        <span className="provider-accordion-baseurl" title={provider.base_url}>{provider.base_url}</span>
        {/* P0-MODEL-FAILOVER: 健康分 + 1h 成功率 + 熔断徽章 */}
        {typeof provider.health_score === "number" && (
          <span className="provider-accordion-score" title="健康分 0..1">
            健 {provider.health_score.toFixed(2)}
          </span>
        )}
        {typeof provider.success_rate_1h === "number" && (
          <span className="provider-accordion-sr" title="1h 成功率">
            {(provider.success_rate_1h * 100).toFixed(0)}%
          </span>
        )}
        {circuitBadge.text && (
          <span className={`provider-accordion-circuit provider-accordion-circuit-${circuitBadge.color}`} title={`熔断器: ${provider.circuit_state}`}>
            {circuitBadge.text}
          </span>
        )}
        <span className={`provider-accordion-dot provider-accordion-dot-${healthColor}`} title={provider.last_health_status ?? "未测"} />
        <span className="provider-accordion-enabled" data-on={provider.enabled}>{provider.enabled ? "启用" : "禁用"}</span>
      </button>
      {expanded && (
        <div className="provider-accordion-body">
          <Field label="Provider 类型">
            <select className="input" value={providerType} onChange={(e) => {
              const t = e.target.value;
              setProviderType(t);
              if (PROVIDER_TYPE_URLS[t] !== undefined) {
                onChange({ base_url: PROVIDER_TYPE_URLS[t] });
              }
            }}>
              <option value="custom">自定义</option>
              <option value="openrouter">OpenRouter</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Google Gemini</option>
              <option value="siliconflow">SiliconFlow</option>
            </select>
          </Field>
          <Field label="名称">
            <input className="input" defaultValue={provider.name} onBlur={(e) => e.target.value !== provider.name && onChange({ name: e.target.value })} />
          </Field>
          <Field label="Base URL">
            <input className="input" defaultValue={provider.base_url} onBlur={(e) => e.target.value !== provider.base_url && onChange({ base_url: e.target.value })} />
          </Field>
          <Field label="API Key">
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                className="input"
                style={{ flex: 1 }}
                type={showApiKey ? "text" : "password"}
                placeholder={provider.has_api_key ? provider.api_key : "未配置, 粘贴新 key"}
                onChange={(e) => setDraft((d) => ({ ...d, api_key: e.target.value }))}
                onBlur={() => draft.api_key && onChange({ api_key: draft.api_key })}
              />
              <button
                type="button"
                className="input"
                style={{ padding: "4px 10px", cursor: "pointer", background: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: 4, whiteSpace: "nowrap" }}
                onClick={() => setShowApiKey((v) => !v)}
                title={showApiKey ? "隐藏 API Key" : "显示 API Key"}
              >
                {showApiKey ? "隐藏" : "显示"}
              </button>
            </div>
          </Field>
          <Field label="默认模型">
            <input className="input" defaultValue={provider.default_model} onBlur={(e) => e.target.value !== provider.default_model && onChange({ default_model: e.target.value })} />
          </Field>
          <Field label="模型列表 (逗号分隔)">
            <input className="input" defaultValue={(provider.model_list ?? []).join(", ")} onBlur={(e) => {
              const list = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
              if (JSON.stringify(list) !== JSON.stringify(provider.model_list ?? [])) onChange({ model_list: list });
            }} />
          </Field>
          <Field label="启用">
            <label className="inline-checkbox">
              <input type="checkbox" defaultChecked={provider.enabled} onChange={(e) => onChange({ enabled: e.target.checked })} />
              启用
            </label>
          </Field>
          <div className="provider-accordion-actions">
            <button onClick={onTest} disabled={busy.test}>{busy.test ? "测试中..." : "测试连接"}</button>
            <button onClick={() => onHealth()} disabled={busy.health}>{busy.health ? "健康检查中..." : "健康检查"}</button>
            <button
              onClick={async () => {
                const list = await onPreviewModels(provider.base_url, draft.api_key ?? "");
                if (Array.isArray(list) && list.length > 0) {
                  setPreviewedModels(list);
                  onChange({ model_list: list });
                }
              }}
              disabled={busy.preview}
            >
              {busy.preview ? "拉取中..." : "拉取模型列表"}
            </button>
            {provider.circuit_state === "open" && (
              <button
                className="circuit-reset"
                onClick={async () => {
                  try {
                    const { resetProviderCircuit } = await import("../../api");
                    await resetProviderCircuit(provider.id);
                    onChange({});  // 触发父组件 reload
                  } catch (e) { /* swallow */ }
                }}
                title="把熔断器重置为 closed"
              >
                重置熔断
              </button>
            )}
            <button onClick={onDelete} className="danger" disabled={busy.delete}>
              {busy.delete ? "删除中..." : "删除"}
            </button>
          </div>
          {previewedModels && previewedModels.length > 0 && (
            <details className="provider-accordion-details">
              <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
                已拉取 {previewedModels.length} 个模型
              </summary>
              <div style={{ maxHeight: 200, overflowY: "auto", padding: "4px 0" }}>
                {previewedModels.map((m, i) => (
                  <div key={i} style={{ fontSize: 12, padding: "2px 8px", fontFamily: "monospace", color: "var(--text-secondary)" }}>{m}</div>
                ))}
              </div>
            </details>
          )}
          {/* P0-MODEL-FAILOVER: 监控数据行 */}
          <div className="provider-accordion-stats">
            <span>1h 成功率: <b>{(provider.success_rate_1h * 100 || 0).toFixed(0)}%</b></span>
            <span>24h 成功率: <b>{(provider.success_rate_24h * 100 || 0).toFixed(0)}%</b></span>
            <span>平均延迟: <b>{provider.avg_latency_ms ?? "—"} ms</b></span>
            <span>连续成功/失败: <b>{provider.consecutive_successes}/{provider.consecutive_failures}</b></span>
            <span>日用量: <b>{provider.daily_request_count} 次 / {provider.daily_token_count} tokens / ${(provider.daily_cost_usd || 0).toFixed(3)}</b></span>
            {provider.last_failure_message && (
              <span className="last-fail">最近失败 ({provider.last_failure_type}): {provider.last_failure_message.slice(0, 100)}</span>
            )}
          </div>
          {provider.last_health_full?.results?.length ? (
            <div className="provider-accordion-details">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
                <b style={{ fontSize: 12 }}>健康检查明细</b>
                <span className="muted small">
                  {provider.last_health_model || provider.default_model} · {provider.last_health_full.score} 分
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6 }}>
                {provider.last_health_full.results.map((it) => (
                  <div
                    key={it.name}
                    style={{
                      border: "1px solid var(--border-secondary)",
                      borderRadius: 4,
                      padding: "6px 8px",
                      background: it.status === "failed"
                        ? "rgba(196,88,88,0.10)"
                        : it.status === "warning"
                          ? "rgba(227,183,95,0.10)"
                          : "rgba(93,156,93,0.08)",
                    }}
                    title={it.raw_preview || it.message}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 6, marginBottom: 3 }}>
                      <span className="mono tiny">{it.name}</span>
                      <span className={`pill tiny ${it.status === "passed" ? "ok" : it.status === "failed" ? "error" : "warn"}`}>
                        {it.status}
                      </span>
                    </div>
                    <div className="muted small" style={{ whiteSpace: "normal" }}>{it.message}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {provider.last_test_message && (
            <div className="provider-accordion-hint">{provider.last_test_message}</div>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="provider-accordion-field">
      <label>{label}</label>
      {children}
    </div>
  );
}
