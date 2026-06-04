/**
 * ModelsPage — 模型配置 (P4: 3 栏布局)
 *
 * 旧版是 Provider 卡片平铺; P4 改成 ShelfLayout 3 栏:
 *   左:   Provider 折叠列表 (ProviderAccordion)
 *   中:   角色绑定矩阵 (AgentRoleMatrix) + "+ 新增 Agent" 按钮
 *   右:   选中 Agent 的详细日志 (AgentRunDetailPanel)
 *
 * 数据接口 (P4 §9):
 *   GET    /api/agent-roles/matrix      矩阵 + 状态
 *   POST   /api/agent-roles             新增
 *   PUT    /api/agent-roles/{id}        更新
 *   DELETE /api/agent-roles/{id}        删除
 *   PUT    /api/agent-roles/{id}/model-binding  改绑
 *   GET    /api/models/providers        Provider CRUD (保留旧 API)
 */
import { useEffect, useMemo, useState } from "react";
import {
  createAgentRole,
  deleteAgentRole,
  getAgentRoleMatrix,
  updateAgentRole,
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  testProvider,
  healthCheckProvider,
  previewProviderModels,
} from "../api";
import type {
  AgentRole,
  AgentRoleCreateBody,
  AgentRoleMatrixItem,
  AgentRoleMatrixResponse,
  AgentRoleUpdateBody,
  ModelProvider,
} from "../types";
import {
  ShelfLayout, ShelfToolbar, ShelfSidePanel,
} from "../components/shelf";
import {
  ProviderAccordion,
  AgentRoleMatrix,
  AgentRunDetailPanel,
  AgentRoleEditor,
} from "../components/models";

export function ModelsPage() {
  const [matrix, setMatrix] = useState<AgentRoleMatrixResponse | null>(null);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [busyProviders, setBusyProviders] = useState<Record<number, { test?: boolean; health?: boolean; preview?: boolean }>>({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<AgentRole | null>(null);
  const [search, setSearch] = useState("");

  // 拉数据
  const load = () => {
    getAgentRoleMatrix()
      .then((m) => {
        setMatrix(m);
        if (selectedRoleId == null && m.items.length > 0) setSelectedRoleId(m.items[0].role.id);
      })
      .catch((e) => setErrorMsg(String(e?.message ?? e)));
    listProviders()
      .then(setProviders)
      .catch((e) => setErrorMsg(String(e?.message ?? e)));
  };
  useEffect(load, []); // eslint-disable-line
  useEffect(() => {
    const h = window.setInterval(load, 8000);
    return () => window.clearInterval(h);
  }, []); // eslint-disable-line

  // 过滤
  const filteredItems = useMemo<AgentRoleMatrixItem[]>(() => {
    if (!matrix) return [];
    if (!search.trim()) return matrix.items;
    const q = search.trim().toLowerCase();
    return matrix.items.filter((it) =>
      it.role.key.toLowerCase().includes(q)
      || it.role.display_name.toLowerCase().includes(q)
      || (it.role.description ?? "").toLowerCase().includes(q)
      || (it.model_name ?? "").toLowerCase().includes(q),
    );
  }, [matrix, search]);

  const selectedItem = useMemo<AgentRoleMatrixItem | null>(() => {
    if (!matrix || selectedRoleId == null) return null;
    return matrix.items.find((it) => it.role.id === selectedRoleId) ?? null;
  }, [matrix, selectedRoleId]);

  // Provider 操作
  const onProviderChange = async (id: number, body: Partial<ModelProvider>) => {
    try {
      await updateProvider(id, body);
      setSuccessMsg("Provider 已保存");
      setTimeout(() => setSuccessMsg(null), 2000);
      load();
    } catch (e: any) {
      setErrorMsg(String(e?.message ?? e));
    }
  };
  const onProviderDelete = async (id: number) => {
    if (!confirm("确认删除这个 Provider?")) return;
    try {
      await deleteProvider(id);
      load();
    } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };
  const onProviderTest = async (id: number) => {
    setBusyProviders((p) => ({ ...p, [id]: { ...p[id], test: true } }));
    try {
      const r = await testProvider(id);
      setSuccessMsg(r.ok ? `${r.message} (${r.latency_ms}ms)` : r.message);
      setErrorMsg(r.ok ? null : (r.suggestion ?? r.message));
      load();
    } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
    finally {
      setBusyProviders((p) => ({ ...p, [id]: { ...p[id], test: false } }));
    }
  };
  const onProviderHealth = async (id: number, model?: string) => {
    setBusyProviders((p) => ({ ...p, [id]: { ...p[id], health: true } }));
    try {
      const r = await healthCheckProvider(id, model);
      setSuccessMsg(`健康检查: ${r.status} · 评分 ${r.score.toFixed(2)}`);
      load();
    } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
    finally {
      setBusyProviders((p) => ({ ...p, [id]: { ...p[id], health: false } }));
    }
  };
  const onProviderPreview = async (id: number, baseUrl: string, apiKey: string) => {
    setBusyProviders((p) => ({ ...p, [id]: { ...p[id], preview: true } }));
    try {
      const r = await previewProviderModels(baseUrl, apiKey);
      setSuccessMsg(`拉到 ${r.models.length} 个模型`);
      load();
      return r.models;
    } catch (e: any) {
      setErrorMsg(String(e?.message ?? e));
      return [];
    } finally {
      setBusyProviders((p) => ({ ...p, [id]: { ...p[id], preview: false } }));
    }
  };

  // Agent 操作
  const onAddAgent = () => {
    setEditingRole(null);
    setEditorOpen(true);
  };
  const onEditAgent = (id: number) => {
    const item = matrix?.items.find((it) => it.role.id === id);
    if (item) {
      setEditingRole(item.role);
      setEditorOpen(true);
    }
  };
  const onDeleteAgent = async (id: number) => {
    const item = matrix?.items.find((it) => it.role.id === id);
    if (!item) return;
    if (["planner", "drafter"].includes(item.role.key)) {
      setErrorMsg("planner / drafter 是核心 Agent, 不能删除");
      return;
    }
    if (!confirm(`确认删除 Agent "${item.role.display_name}"?`)) return;
    try {
      await deleteAgentRole(id);
      if (selectedRoleId === id) setSelectedRoleId(null);
      load();
    } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };
  const onSaveAgent = async (body: AgentRoleCreateBody | AgentRoleUpdateBody) => {
    try {
      if (editingRole) {
        await updateAgentRole(editingRole.id, body as AgentRoleUpdateBody);
        setSuccessMsg(`已更新 ${editingRole.display_name}`);
      } else {
        const r = await createAgentRole(body as AgentRoleCreateBody);
        setSuccessMsg(`已创建 ${r.display_name}`);
        setSelectedRoleId(r.id);
      }
      setEditorOpen(false);
      setEditingRole(null);
      setTimeout(() => setSuccessMsg(null), 2000);
      load();
    } catch (e: any) {
      setErrorMsg(String(e?.message ?? e));
      throw e;
    }
  };

  return (
    <>
      <ShelfLayout
        title="模型配置"
        subtitle="Provider 折叠 + 角色绑定矩阵 + Agent 工作情况。P4 §1-§7。"
        breadcrumb={[{ label: "模型配置" }]}
        left={
          <>
            <ShelfToolbar>
              <input
                className="input"
                placeholder="🔍 搜索 Provider"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <button
                className="primary"
                onClick={async () => {
                  const name = prompt("新 Provider 名称:");
                  if (!name) return;
                  try {
                    await createProvider({ name, base_url: "https://api.openai.com/v1", enabled: true });
                    load();
                    setSuccessMsg(`已创建 ${name}`);
                  } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
                }}
              >
                + 新增 Provider
              </button>
            </ShelfToolbar>

            {errorMsg && (
              <ShelfSidePanel title="错误" accentColor="red">
                <div className="muted small" style={{ whiteSpace: "pre-wrap" }}>{errorMsg}</div>
              </ShelfSidePanel>
            )}
            {successMsg && (
              <ShelfSidePanel title="成功" accentColor="green">
                <div className="muted small">{successMsg}</div>
              </ShelfSidePanel>
            )}

            <ShelfSidePanel title="Provider 列表" accentColor="blue">
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
                共 {providers.length} 个 · 启用 {providers.filter((p) => p.enabled).length}
              </div>
            </ShelfSidePanel>

            {providers.map((p) => (
              <ProviderAccordion
                key={p.id}
                provider={p}
                onChange={(body) => onProviderChange(p.id, body)}
                onDelete={() => onProviderDelete(p.id)}
                onTest={() => onProviderTest(p.id)}
                onHealth={(model) => onProviderHealth(p.id, model)}
                onPreviewModels={(baseUrl, apiKey) => onProviderPreview(p.id, baseUrl, apiKey)}
                busy={busyProviders[p.id] ?? {}}
              />
            ))}
          </>
        }
        center={
          matrix ? (
            <AgentRoleMatrix
              items={filteredItems}
              selectedId={selectedRoleId}
              onSelect={setSelectedRoleId}
              onAddAgent={onAddAgent}
              onEdit={onEditAgent}
              onDelete={onDeleteAgent}
            />
          ) : (
            <div className="muted small" style={{ padding: 24 }}>加载矩阵…</div>
          )
        }
        right={
          <AgentRunDetailPanel item={selectedItem} />
        }
      />

      <AgentRoleEditor
        open={editorOpen}
        mode={editingRole ? "edit" : "create"}
        initial={editingRole}
        onClose={() => { setEditorOpen(false); setEditingRole(null); }}
        onSave={onSaveAgent}
      />
    </>
  );
}
