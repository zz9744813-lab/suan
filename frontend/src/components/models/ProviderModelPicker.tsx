/**
 * ProviderModelPicker — Provider + Model 联合选择器
 *
 * 功能:
 *   Provider 下拉 (只显示 enabled=true)
 *   模型下拉 (从 Provider 缓存或手动输入)
 *   手动输入模型名
 *   刷新模型列表
 *   显示 Provider 状态
 */
import { useState, useEffect, useCallback } from "react";
import type { ModelProvider } from "../../types";
import { healthCheckProvider, testProvider } from "../../api";

interface ProviderModelPickerProps {
  providers: ModelProvider[];
  providerId: number | null;
  modelName: string;
  onProviderChange: (id: number | null) => void;
  onModelChange: (name: string) => void;
  allowManualInput?: boolean;
}

export function ProviderModelPicker({
  providers,
  providerId,
  modelName,
  onProviderChange,
  onModelChange,
  allowManualInput = true,
}: ProviderModelPickerProps) {
  const [modelList, setModelList] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [healthStatus, setHealthStatus] = useState<{ score: number; status: string } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const enabledProviders = providers.filter((p) => p.enabled);
  const currentProvider = providers.find((p) => p.id === providerId);

  // 当选中 Provider 变化时优先使用缓存；用户点击「拉取」时强制走后端，
  // 让后端使用数据库中保存的真实 API Key。前端拿到的是掩码 key，
  // 不能再拿它去请求 preview-models。
  const fetchModels = useCallback(async (forceRefresh = false) => {
    const p = currentProvider;
    if (!p) {
      setModelList([]);
      return;
    }
    // 如果 Provider 已有缓存的模型列表，直接使用
    if (!forceRefresh && p.model_list && p.model_list.length > 0) {
      setModelList(p.model_list.filter((m) => typeof m === "string") as string[]);
      return;
    }
    // 已保存的 Provider 用 /test 刷新模型列表；该端点会使用后端保存的真实 key。
    setLoadingModels(true);
    setErrorMsg(null);
    try {
      const r = await testProvider(p.id);
      if (!r.ok) {
        throw new Error(r.suggestion ? `${r.message}；${r.suggestion}` : r.message);
      }
      if (!r.models || r.models.length === 0) {
        throw new Error(r.message || "Provider 未返回模型列表");
      }
      setModelList(r.models);
    } catch (e: any) {
      setErrorMsg(`无法拉取模型列表: ${e?.message ?? String(e)}`);
      setModelList([]);
    } finally {
      setLoadingModels(false);
    }
  }, [currentProvider]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  // 健康检查
  const handleHealthCheck = async () => {
    if (!providerId) return;
    try {
      const r = await healthCheckProvider(providerId, modelName || undefined);
      setHealthStatus({ score: r.score, status: r.status });
    } catch (e: any) {
      setErrorMsg(`健康检查失败: ${e?.message ?? String(e)}`);
    }
  };

  useEffect(() => {
    setHealthStatus(null);
  }, [providerId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Provider 下拉 */}
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        <select
          className="input"
          value={providerId ?? ""}
          onChange={(e) => {
            const id = e.target.value ? Number(e.target.value) : null;
            onProviderChange(id);
            if (id !== providerId) {
              onModelChange(""); // Provider 切换时清空模型
              setHealthStatus(null);
              setErrorMsg(null);
            }
          }}
          style={{ flex: 1 }}
        >
          <option value="">-- 选择 Provider --</option>
          {enabledProviders.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} (#{p.id})
            </option>
          ))}
        </select>
        {providerId && (
          <button
            className="tiny"
            onClick={handleHealthCheck}
            title="健康检查"
            style={{ fontSize: 11 }}
          >
            {healthStatus ? `✓ ${(healthStatus.score * 100).toFixed(0)}%` : "体检"}
          </button>
        )}
      </div>

      {/* Provider 状态指示 */}
      {currentProvider && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", gap: 8 }}>
          <span>{currentProvider.base_url}</span>
          {currentProvider.default_model && (
            <span>默认: {currentProvider.default_model}</span>
          )}
          {healthStatus && (
            <span style={{ color: healthStatus.score >= 0.5 ? "var(--success)" : "var(--warning)" }}>
              状态: {healthStatus.status} ({healthStatus.score.toFixed(2)})
            </span>
          )}
        </div>
      )}

      {/* 模型下拉 / 输入 */}
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {modelList.length > 0 ? (
          <select
            className="input"
            value={modelName}
            onChange={(e) => onModelChange(e.target.value)}
            style={{ flex: 1 }}
          >
            <option value="">-- 选择模型 --</option>
            {modelList.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
            {allowManualInput && modelName && !modelList.includes(modelName) && (
              <option value={modelName}>{modelName} (手动输入)</option>
            )}
          </select>
        ) : (
          <input
            className="input"
            placeholder="Model 名称 (如 gpt-4, claude-3.5-sonnet)"
            value={modelName}
            onChange={(e) => onModelChange(e.target.value)}
            style={{ flex: 1 }}
          />
        )}

        {/* 模型列表拉取按钮 */}
        {currentProvider && (
          <button
            className="tiny"
            onClick={() => fetchModels(true)}
            disabled={loadingModels}
            title="刷新模型列表"
            style={{ fontSize: 11 }}
          >
            {loadingModels ? "拉取中..." : "拉取"}
          </button>
        )}
      </div>

      {errorMsg && (
        <div style={{ fontSize: 11, color: "var(--danger)" }}>{errorMsg}</div>
      )}
    </div>
  );
}
