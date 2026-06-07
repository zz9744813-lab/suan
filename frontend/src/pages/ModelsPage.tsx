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
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createAgentRole,
  deleteAgentRole,
  getAgentRoleMatrix,
  updateAgentRole,
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  getProviderDeletePreview,
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
  ProviderDeletePreview,
} from "../types";
import {
  ShelfLayout, ShelfToolbar, ShelfSidePanel,
} from "../components/shelf";
import {
  ProviderAccordion,
  AgentRoleMatrix,
  AgentRunDetailPanel,
  AgentRoleEditor,
  AgentRoleEditorModal,
  FirstRunGuide,
  AutoConfigureModal,
  ConfirmDialog,
} from "../components/models";

export function ModelsPage() {
  const [matrix, setMatrix] = useState<AgentRoleMatrixResponse | null>(null);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [busyProviders, setBusyProviders] = useState<Record<number, { test?: boolean; health?: boolean; preview?: boolean }>>({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [editingRole, setEditingRole] = useState<AgentRole | null>(null);
  const [createEditorOpen, setCreateEditorOpen] = useState(false);
  const [bindingEditorOpen, setBindingEditorOpen] = useState(false);
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [showFirstRunGuide, setShowFirstRunGuide] = useState(false);
  const firstRunShown = useRef(false);
  const [showAutoConfigure, setShowAutoConfigure] = useState(false);
  const [autoConfigureProvider, setAutoConfigureProvider] = useState<ModelProvider | null>(null);
  const [expandedProviderId, setExpandedProviderId] = useState<number | null>(null);
  // P-Delete-Preview: which provider the delete dialog is open
  // for, and the preflight summary we just fetched. ``null`` means
  // the dialog is closed. We keep the id + the summary side by side
  // so the dialog can show the cascade details without a second
  // round-trip on every re-render.
  const [deletePreview, setDeletePreview] = useState<{
    providerId: number;
    preview: ProviderDeletePreview;
  } | null>(null);
  // P-Delete-Preview: per-provider busy flag for the delete flow
  // (used to disable the confirm button while the DELETE call is
  // in flight; the dialog also tracks its own busy state but we
  // want the accordion's delete button disabled too).
  const [deletingProviderId, setDeletingProviderId] = useState<number | null>(null);

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

  // 首次运行引导: 只有 stub Provider 时弹窗
  useEffect(() => {
    if (firstRunShown.current) return;
    if (providers.length === 1) {
      const p = providers[0];
      if (p.name === "stub" || p.base_url?.startsWith("mock://")) {
        setShowFirstRunGuide(true);
        firstRunShown.current = true;
      }
    }
  }, [providers]);

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

  const editingItem = useMemo<AgentRoleMatrixItem | null>(() => {
    if (!matrix || editingRoleId == null) return null;
    return matrix.items.find((it) => it.role.id === editingRoleId) ?? null;
  }, [matrix, editingRoleId]);

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
    // P-Delete-Preview: replaced the native `confirm()` with a
    // project-styled dialog. First we fetch the preflight summary
    // (which role bindings / call events will cascade) and only
    // then open the dialog. If the fetch fails (404, network, ...)
    // we surface the error in the page-level error banner and
    // bail — no dialog appears, no destructive action taken.
    if (deletePreview?.providerId === id) {
      // Already showing the dialog for this provider; clicking
      // the delete button again is a no-op (the dialog handles
      // its own confirm/cancel).
      return;
    }
    try {
      const preview = await getProviderDeletePreview(id);
      setDeletePreview({ providerId: id, preview });
    } catch (e: any) {
      setErrorMsg(`无法加载删除预检：${e?.message ?? e}`);
    }
  };
  // P-Delete-Preview: actual DELETE call. Called from the
  // ConfirmDialog's onConfirm handler. The dialog handles its own
  // busy/disabled state; we set a page-level flag so the
  // accordion's "删除" button also reflects in-flight state.
  const onProviderDeleteConfirm = async () => {
    if (!deletePreview) return;
    const { providerId, preview } = deletePreview;
    setDeletingProviderId(providerId);
    try {
      await deleteProvider(providerId);
      setDeletePreview(null);
      const cascade = preview.will_cascade_role_bindings.length;
      if (cascade > 0) {
        setSuccessMsg(
          `已删除 Provider「${preview.provider_name}」及 ${cascade} 个角色绑定`,
        );
      } else {
        setSuccessMsg(`已删除 Provider「${preview.provider_name}」`);
      }
      setTimeout(() => setSuccessMsg(null), 3000);
      load();
    } finally {
      setDeletingProviderId(null);
    }
  };
  const onProviderDeleteCancel = () => {
    // ``ConfirmDialog`` calls this on cancel and on backdrop
    // click. We just drop the preflight state; the dialog itself
    // unmounts because ``deletePreview`` is null.
    setDeletePreview(null);
  };
  const onProviderTest = async (id: number) => {
    setBusyProviders((p) => ({ ...p, [id]: { ...p[id], test: true } }));
    try {
      const r = await testProvider(id);
      if (r.ok) {
        setSuccessMsg(`${r.message} (${r.latency_ms}ms)`);
        setErrorMsg(null);
      } else {
        setSuccessMsg(null);
        setErrorMsg(r.suggestion ? `${r.message}\n${r.suggestion}` : r.message);
      }
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
      const failedItems = r.results.filter((it) => it.status === "failed");
      const warningItems = r.results.filter((it) => it.status === "warning");
      if (r.ok) {
        const warning = warningItems[0];
        setSuccessMsg(
          warning
            ? `健康检查可用: ${r.model} · ${r.score} 分 · ${r.latency_ms}ms；提醒：${warning.name} ${warning.message}`
            : `健康检查通过: ${r.model} · ${r.score} 分 · ${r.latency_ms}ms`,
        );
        setErrorMsg(null);
      } else {
        setSuccessMsg(null);
        const detail = failedItems[0] ?? warningItems[0];
        setErrorMsg(
          detail
            ? `${r.message}\n${detail.name}: ${detail.message}${detail.suggestion ? `\n${detail.suggestion}` : ""}`
            : r.message,
        );
      }
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
      if (r.ok) {
        setSuccessMsg(`拉到 ${r.models.length} 个模型`);
        setErrorMsg(null);
      } else {
        setSuccessMsg(null);
        setErrorMsg(r.suggestion ? `${r.message}\n${r.suggestion}` : r.message);
      }
      load();
      return r.models;
    } catch (e: any) {
      setErrorMsg(String(e?.message ?? e));
      return [];
    } finally {
      setBusyProviders((p) => ({ ...p, [id]: { ...p[id], preview: false } }));
    }
  };

  // 新增 Provider (支持快速添加 OpenRouter/DeepSeek/自定义)
  const onAddProvider = async (type?: string) => {
    try {
      let newProvider: ModelProvider | null = null;
      if (type === "openrouter") {
        newProvider = await createProvider({ name: "OpenRouter", base_url: "https://openrouter.ai/api/v1", enabled: true });
        setSuccessMsg("已快速创建 OpenRouter");
      } else if (type === "deepseek") {
        newProvider = await createProvider({ name: "DeepSeek", base_url: "https://api.deepseek.com/v1", enabled: true });
        setSuccessMsg("已快速创建 DeepSeek");
      } else {
        const name = prompt("新 Provider 名称:");
        if (!name) return;
        newProvider = await createProvider({ name, base_url: "https://api.openai.com/v1", enabled: true });
        setSuccessMsg(`已创建 ${name}`);
      }
      if (newProvider) setExpandedProviderId(newProvider.id);
      load();
      // 检测是否是第一个真实 Provider（之前只有 stub）
      if (newProvider && providers.length === 1) {
        const only = providers[0];
        if (only.name === "stub" || only.base_url?.startsWith("mock://")) {
          setAutoConfigureProvider(newProvider);
          setShowAutoConfigure(true);
        }
      }
    } catch (e: any) { setErrorMsg(String(e?.message ?? e)); }
  };

  // Agent 操作
  // 新增 Agent：走旧基础创建弹窗 (只有基础信息)
  const onAddAgent = () => {
    setEditingRole(null);
    setCreateEditorOpen(true);
  };
  // 编辑已有 Agent：走新 AgentRoleEditorModal (三 Tab: 基础信息 / 模型绑定 / Prompt 绑定)
  const onEditAgent = (id: number) => {
    const item = matrix?.items.find((it) => it.role.id === id);
    if (!item) return;
    setEditingRoleId(id);
    setBindingEditorOpen(true);
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
      setCreateEditorOpen(false);
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
                onClick={() => onAddProvider()}
              >
                + 添加 API Provider
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

            {/* P0-D: Global stub warning */}
            {(() => {
              const stubCount = matrix?.items.filter(it => 
                it.provider_name === 'stub' || (it.model_name && it.model_name.startsWith('mock-'))
              ).length ?? 0;
              const totalCount = matrix?.items.length ?? 0;
              const halfStub = totalCount > 0 && stubCount / totalCount > 0.5;
              
              if (!halfStub) return null;
              return (
                <ShelfSidePanel title="⚠️ 模型警告" accentColor="gold">
                  <div style={{fontSize: 12, lineHeight: 1.6}}>
                    {stubCount}/{totalCount} 个 Agent 仍使用 mock 模型，生产写作不会调用真实 API。
                    <br />
                    <span style={{color: 'var(--accent)'}}>请添加真实 API Provider 并一键配置 Agent 模型绑定。</span>
                  </div>
                </ShelfSidePanel>
              );
            })()}

            {providers.map((p) => (
              <ProviderAccordion
                key={p.id}
                provider={p}
                defaultExpanded={p.id === expandedProviderId}
                onChange={(body) => onProviderChange(p.id, body)}
                onDelete={() => onProviderDelete(p.id)}
                onTest={() => onProviderTest(p.id)}
                onHealth={(model) => onProviderHealth(p.id, model)}
                onPreviewModels={(baseUrl, apiKey) => onProviderPreview(p.id, baseUrl, apiKey)}
                busy={{
                  ...(busyProviders[p.id] ?? {}),
                  // P-Delete-Preview: also flip on the delete button
                  // while a DELETE is in flight. The button label
                  // stays "删除" — we don't surface a spinner inside
                  // the accordion because the dialog already has one.
                  delete: deletingProviderId === p.id,
                }}
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

      {/* 新增 Agent：使用基础创建弹窗 (旧 AgentRoleEditor，仅基础信息) */}
      <AgentRoleEditor
        open={createEditorOpen}
        mode="create"
        initial={null}
        onClose={() => {
          setCreateEditorOpen(false);
          setEditingRole(null);
        }}
        onSave={onSaveAgent}
      />

      {/* 编辑已有 Agent：使用 AgentRoleEditorModal (三 Tab: 基础信息 / 模型绑定 / Prompt 绑定) */}
      {editingItem && (
        <AgentRoleEditorModal
          open={bindingEditorOpen}
          role={editingItem.role}
          binding={editingItem.binding}
          promptBinding={editingItem.prompt_binding}
          onClose={() => {
            setBindingEditorOpen(false);
            setEditingRoleId(null);
          }}
          onSaved={() => {
            load();
            const name = editingItem?.role.display_name ?? "Agent";
            setSuccessMsg(`已更新 ${name}`);
            setTimeout(() => setSuccessMsg(null), 2000);
          }}
        />
      )}

      {/* 首次运行引导 */}
      <FirstRunGuide
        open={showFirstRunGuide}
        onClose={() => setShowFirstRunGuide(false)}
        onCreateProvider={async (type) => {
          setShowFirstRunGuide(false);
          await onAddProvider(type);
        }}
      />

      {/* 一键自动配置 */}
      <AutoConfigureModal
        open={showAutoConfigure}
        provider={autoConfigureProvider}
        matrixItems={matrix?.items ?? []}
        onClose={() => {
          setShowAutoConfigure(false);
          setAutoConfigureProvider(null);
        }}
        onConfigured={() => {
          setShowAutoConfigure(false);
          setAutoConfigureProvider(null);
          load();
        }}
      />

      {/* P-Delete-Preview: 删除 Provider 二次确认弹窗. 只在
          ``deletePreview`` 不为 null 时挂载; 弹窗自己处理
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
          confirmDisabled={deletingProviderId === deletePreview.providerId}
          onCancel={onProviderDeleteCancel}
          onConfirm={onProviderDeleteConfirm}
        />
      )}
    </>
  );
}
