/* P10: Agent 分层记忆池 — 三栏布局
 * 左侧: 项目/Agent 列表
 * 中间: 四层记忆看板
 * 右侧: 记忆详情面板
 */
import { useState, useEffect, useCallback } from "react";
import { useProjectStore } from "../stores/projectStore";
import {
  getAgentMemoryStats,
  getAgentMemoryAgents,
  listAgentMemoryEntries,
  getAgentMemoryDetail,
  promoteAgentMemory,
  demoteAgentMemory,
  archiveAgentMemory,
  consolidateAgentMemory,
  type AgentMemoryStats,
  type MemoryProjectStats,
  type MemoryEntryListItem,
  type MemoryEntryDetail,
} from "../api";

const LAYER_META: Record<string, { label: string; icon: string; color: string; gradient: string }> = {
  temporary: { label: "临时记忆", icon: "⏳", color: "#38bdf8", gradient: "linear-gradient(135deg, #0ea5e9, #06b6d4)" },
  task: { label: "任务记忆", icon: "📋", color: "#fb923c", gradient: "linear-gradient(135deg, #f97316, #ef4444)" },
  long_term: { label: "长时记忆", icon: "🧠", color: "#4ade80", gradient: "linear-gradient(135deg, #22c55e, #10b981)" },
  permanent: { label: "永久记忆", icon: "🔒", color: "#a78bfa", gradient: "linear-gradient(135deg, #7c3aed, #1e1b4b)" },
};

const AGENT_ICONS: Record<string, string> = {
  planner: "📐", drafter: "✍️", critic: "🔍", rewriter: "🔄",
  continuity: "🔗", reader: "📖", memory_update: "💾",
  chief: "🎯", skill_builder: "🛠️",
};

function HealthBadge({ score }: { score: number }) {
  const color = score >= 0.8 ? "#4ade80" : score >= 0.5 ? "#38bdf8" : score >= 0.2 ? "#a78bfa" : "#f87171";
  return <span style={{ color, fontSize: 12, fontWeight: 600 }}>{(score * 100).toFixed(0)}%</span>;
}

function ConfidenceBar({ value }: { value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: "var(--bg-base)" }}>
        <div style={{ width: `${value * 100}%`, height: "100%", borderRadius: 2, background: value >= 0.8 ? "#4ade80" : value >= 0.5 ? "#fbbf24" : "#f87171" }} />
      </div>
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{(value * 100).toFixed(0)}%</span>
    </div>
  );
}

// ============================================================
// 左侧面板: Agent 列表
// ============================================================
function AgentSidebar({
  projectId,
  stats,
  agents,
  selectedAgent,
  onSelectAgent,
}: {
  projectId: number;
  stats: MemoryProjectStats | null;
  agents: AgentMemoryStats[];
  selectedAgent: string;
  onSelectAgent: (role: string) => void;
}) {
  return (
    <aside className="am-sidebar">
      <div className="am-sidebar-header">
        <h3>项目记忆库</h3>
        {stats && (
          <div className="am-stats-summary">
            <span className="am-stat-chip">共 {stats.total} 条</span>
            {stats.conflict_count > 0 && <span className="am-stat-chip am-stat-conflict">{stats.conflict_count} 冲突</span>}
          </div>
        )}
      </div>
      {stats && (
        <div className="am-layer-summary">
          {Object.entries(stats.by_layer).map(([layer, count]) => (
            <div key={layer} className="am-layer-chip" style={{ borderLeftColor: LAYER_META[layer]?.color || "#888" }}>
              <span>{LAYER_META[layer]?.icon} {LAYER_META[layer]?.label || layer}</span>
              <strong>{count}</strong>
            </div>
          ))}
        </div>
      )}
      <div className="am-agent-list">
        <div
          className={`am-agent-item ${selectedAgent === "all" ? "am-agent-active" : ""}`}
          onClick={() => onSelectAgent("all")}
        >
          <span className="am-agent-icon">📊</span>
          <div className="am-agent-info">
            <span className="am-agent-name">全部 Agent</span>
            <span className="am-agent-count">{stats?.total || 0} 条记忆</span>
          </div>
        </div>
        {agents.map(a => (
          <div
            key={a.agent_role}
            className={`am-agent-item ${selectedAgent === a.agent_role ? "am-agent-active" : ""}`}
            onClick={() => onSelectAgent(a.agent_role)}
          >
            <span className="am-agent-icon">{AGENT_ICONS[a.agent_role] || "🤖"}</span>
            <div className="am-agent-info">
              <span className="am-agent-name">{a.agent_name || a.agent_role}</span>
              <span className="am-agent-count">
                {a.memory_count} 条 · <HealthBadge score={a.health_score} />
                {a.conflict_count > 0 && <span style={{ color: "#f87171", marginLeft: 4 }}>⚠{a.conflict_count}</span>}
              </span>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

// ============================================================
// 中间面板: 四层记忆看板
// ============================================================
function MemoryBoard({
  entries,
  selectedLayer,
  onSelectLayer,
  selectedMemoryId,
  onSelectMemory,
  query,
  onQueryChange,
  onConsolidate,
  consolidating,
}: {
  entries: MemoryEntryListItem[];
  selectedLayer: string;
  onSelectLayer: (layer: string) => void;
  selectedMemoryId: number | null;
  onSelectMemory: (id: number) => void;
  query: string;
  onQueryChange: (q: string) => void;
  onConsolidate: () => void;
  consolidating: boolean;
}) {
  const layers = ["temporary", "task", "long_term", "permanent"] as const;
  const grouped = layers.reduce((acc, layer) => {
    acc[layer] = entries.filter(e => e.memory_layer === layer);
    return acc;
  }, {} as Record<string, MemoryEntryListItem[]>);

  return (
    <main className="am-board">
      <div className="am-board-toolbar">
        <input
          className="am-search"
          type="text"
          placeholder="搜索记忆标题、内容、标签..."
          value={query}
          onChange={e => onQueryChange(e.target.value)}
        />
        <div className="am-layer-tabs">
          <button className={`am-layer-tab ${selectedLayer === "all" ? "am-layer-tab-active" : ""}`} onClick={() => onSelectLayer("all")}>全部</button>
          {layers.map(l => (
            <button
              key={l}
              className={`am-layer-tab ${selectedLayer === l ? "am-layer-tab-active" : ""}`}
              onClick={() => onSelectLayer(l)}
              style={selectedLayer === l ? { borderBottomColor: LAYER_META[l].color } : undefined}
            >
              {LAYER_META[l].icon} {LAYER_META[l].label}
              {grouped[l]?.length > 0 && <span className="am-layer-count">{grouped[l].length}</span>}
            </button>
          ))}
        </div>
        <button className="am-btn am-btn-consolidate" onClick={onConsolidate} disabled={consolidating}>
          {consolidating ? "整理中..." : "🔄 运行记忆整理"}
        </button>
      </div>
      <div className="am-board-content">
        {(selectedLayer === "all" ? layers : [selectedLayer as typeof layers[number]]).map(layer => (
          <MemoryLayerSection
            key={layer}
            layer={layer}
            entries={grouped[layer] || []}
            selectedMemoryId={selectedMemoryId}
            onSelectMemory={onSelectMemory}
          />
        ))}
        {entries.length === 0 && (
          <div className="am-empty">
            <div className="am-empty-icon">🧠</div>
            <h3>项目记忆库还是空的</h3>
            <p>Agent 生成内容后会自动写入记忆。你也可以手动创建记忆。</p>
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>记忆分为四层：临时 → 任务 → 长时 → 永久，自动提升与过期。</p>
          </div>
        )}
      </div>
    </main>
  );
}

function MemoryLayerSection({
  layer,
  entries,
  selectedMemoryId,
  onSelectMemory,
}: {
  layer: string;
  entries: MemoryEntryListItem[];
  selectedMemoryId: number | null;
  onSelectMemory: (id: number) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const meta = LAYER_META[layer] || { label: layer, icon: "📦", color: "#888", gradient: "none" };

  return (
    <section className="am-layer-section">
      <div className="am-layer-header" style={{ borderImage: meta.gradient + " 1" }} onClick={() => setCollapsed(!collapsed)}>
        <span>{meta.icon} {meta.label}</span>
        <span className="am-layer-header-count">{entries.length} 条 {collapsed ? "▶" : "▼"}</span>
      </div>
      {!collapsed && (
        <div className="am-layer-cards">
          {entries.map(entry => (
            <div
              key={entry.id}
              className={`am-card ${selectedMemoryId === entry.id ? "am-card-selected" : ""} ${entry.is_conflicted ? "am-card-conflicted" : ""}`}
              onClick={() => onSelectMemory(entry.id)}
            >
              <div className="am-card-top-bar" style={{ background: meta.gradient }} />
              <div className="am-card-body">
                <div className="am-card-title-row">
                  <span className="am-card-title">{entry.title}</span>
                  <div className="am-card-badges">
                    {entry.is_locked && <span className="am-badge am-badge-locked">🔒</span>}
                    {entry.is_conflicted && <span className="am-badge am-badge-conflict">⚠冲突</span>}
                    {entry.is_duplicate_candidate && <span className="am-badge am-badge-dup">重复?</span>}
                  </div>
                </div>
                <p className="am-card-preview">{entry.content_preview}</p>
                <div className="am-card-tags">
                  {entry.tags.slice(0, 3).map(t => <span key={t} className="am-tag">{t}</span>)}
                </div>
                <div className="am-card-meta">
                  <span className="am-card-type">{entry.memory_type}</span>
                  <ConfidenceBar value={entry.confidence} />
                  <span className="am-card-usage">×{entry.usage_count}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ============================================================
// 右侧面板: 记忆详情
// ============================================================
function MemoryDetail({
  detail,
  onPromote,
  onDemote,
  onArchive,
}: {
  detail: MemoryEntryDetail | null;
  onPromote: (id: number, target: string) => void;
  onDemote: (id: number, target: string) => void;
  onArchive: (id: number) => void;
}) {
  if (!detail) {
    return (
      <aside className="am-detail am-detail-empty">
        <div className="am-detail-empty-content">
          <span style={{ fontSize: 40 }}>🧠</span>
          <p>点击左侧记忆卡片查看详情</p>
        </div>
      </aside>
    );
  }

  const meta = LAYER_META[detail.memory_layer] || { label: detail.memory_layer, icon: "📦", color: "#888", gradient: "none" };
  const currentLayerIdx = ["temporary", "task", "long_term", "permanent"].indexOf(detail.memory_layer);

  return (
    <aside className="am-detail">
      <div className="am-detail-top-bar" style={{ background: meta.gradient }} />
      <div className="am-detail-content">
        <div className="am-detail-header">
          <h2 className="am-detail-title">{detail.title}</h2>
          <div className="am-detail-badges">
            <span className="am-badge" style={{ background: meta.color + "22", color: meta.color }}>
              {meta.icon} {meta.label}
            </span>
            <span className="am-badge">{detail.memory_type}</span>
            <span className="am-badge">{detail.visibility}</span>
            {detail.is_locked && <span className="am-badge am-badge-locked">🔒 锁定</span>}
            {detail.is_conflicted && <span className="am-badge am-badge-conflict">⚠ 冲突</span>}
          </div>
        </div>

        <div className="am-detail-section">
          <h4>内容</h4>
          <div className="am-detail-content-text">{detail.content}</div>
          {detail.summary && (
            <div className="am-detail-summary"><strong>摘要：</strong>{detail.summary}</div>
          )}
        </div>

        <div className="am-detail-section">
          <h4>指标</h4>
          <div className="am-detail-metrics">
            <div className="am-metric"><span>置信度</span><ConfidenceBar value={detail.confidence} /></div>
            <div className="am-metric"><span>重要性</span><ConfidenceBar value={detail.importance} /></div>
            <div className="am-metric"><span>健康度</span><HealthBadge score={detail.health_score} /></div>
            <div className="am-metric"><span>使用次数</span><strong>{detail.usage_count}</strong></div>
          </div>
        </div>

        <div className="am-detail-section">
          <h4>来源</h4>
          <div className="am-detail-source">
            <span>类型: {detail.source_type}</span>
            {detail.source_quote && <blockquote className="am-source-quote">{detail.source_quote}</blockquote>}
            {detail.agent_role && <span>写入者: {detail.agent_role}</span>}
          </div>
        </div>

        <div className="am-detail-section">
          <h4>标签</h4>
          <div className="am-detail-tags">
            {detail.tags.map(t => <span key={t} className="am-tag">{t}</span>)}
          </div>
        </div>

        {detail.links && detail.links.length > 0 && (
          <div className="am-detail-section">
            <h4>关系 ({detail.links.length})</h4>
            {detail.links.map(link => (
              <div key={link.id} className="am-link-item">
                <span className="am-link-type">{link.relation_type}</span>
                <span className="am-link-desc">{link.description || `记忆 ${link.target_memory_id}`}</span>
              </div>
            ))}
          </div>
        )}

        {detail.audit_logs && detail.audit_logs.length > 0 && (
          <div className="am-detail-section">
            <h4>审计日志 ({detail.audit_logs.length})</h4>
            {detail.audit_logs.slice(0, 5).map(log => (
              <div key={log.id} className="am-audit-item">
                <span className="am-audit-action">{log.action}</span>
                <span className="am-audit-actor">{log.actor_type}/{log.actor_role || "?"}</span>
                <span className="am-audit-reason">{log.reason}</span>
              </div>
            ))}
          </div>
        )}

        <div className="am-detail-section am-detail-actions">
          <h4>操作</h4>
          <div className="am-action-buttons">
            {currentLayerIdx < 3 && (
              <button
                className="am-btn am-btn-promote"
                onClick={() => {
                  const next = ["temporary", "task", "long_term", "permanent"][currentLayerIdx + 1];
                  onPromote(detail.id, next);
                }}
              >
                ↑ 提升到{LAYER_META[["task", "long_term", "permanent"][currentLayerIdx]]?.label}
              </button>
            )}
            {currentLayerIdx > 0 && !detail.is_locked && (
              <button className="am-btn am-btn-demote" onClick={() => {
                const prevLayer = ["temporary", "task", "long_term", "permanent"][currentLayerIdx - 1];
                onDemote(detail.id, prevLayer);
              }}>
                ↓ 降级到{LAYER_META[["temporary", "task", "long_term"][currentLayerIdx - 1]]?.label}
              </button>
            )}
            {!detail.is_locked && (
              <button className="am-btn am-btn-archive" onClick={() => onArchive(detail.id)}>
                📦 归档
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

// ============================================================
// 主页面
// ============================================================
export function AgentMemoryPage() {
  const { currentProjectId } = useProjectStore();
  const projectId = currentProjectId || 1;

  const [stats, setStats] = useState<MemoryProjectStats | null>(null);
  const [agents, setAgents] = useState<AgentMemoryStats[]>([]);
  const [entries, setEntries] = useState<MemoryEntryListItem[]>([]);
  const [detail, setDetail] = useState<MemoryEntryDetail | null>(null);

  const [selectedAgent, setSelectedAgent] = useState<string>("all");
  const [selectedLayer, setSelectedLayer] = useState<string>("all");
  const [selectedMemoryId, setSelectedMemoryId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [consolidating, setConsolidating] = useState(false);

  // 加载统计和 Agent 列表
  const loadMeta = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        getAgentMemoryStats(projectId),
        getAgentMemoryAgents(projectId),
      ]);
      setStats(s);
      setAgents(a.items);
    } catch { /* ignore */ }
  }, [projectId]);

  // 加载记忆列表
  const loadEntries = useCallback(async () => {
    try {
      const params: Record<string, string | number | boolean | undefined> = {};
      if (selectedAgent !== "all") params.agent_role = selectedAgent;
      if (selectedLayer !== "all") params.memory_layer = selectedLayer;
      if (query) params.q = query;
      const res = await listAgentMemoryEntries(projectId, params);
      setEntries(res.items);
    } catch { /* ignore */ }
  }, [projectId, selectedAgent, selectedLayer, query]);

  // 加载详情
  const loadDetail = useCallback(async (id: number) => {
    try {
      const res = await getAgentMemoryDetail(id);
      setDetail(res);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { loadEntries(); }, [loadEntries]);
  useEffect(() => { if (selectedMemoryId) loadDetail(selectedMemoryId); }, [selectedMemoryId, loadDetail]);

  const handlePromote = async (id: number, target: string) => {
    try {
      await promoteAgentMemory(id, { target_layer: target, reason: "用户手动提升" });
      loadEntries();
      if (selectedMemoryId === id) loadDetail(id);
      loadMeta();
    } catch { /* ignore */ }
  };

  const handleDemote = async (id: number, target: string) => {
    try {
      await demoteAgentMemory(id, { target_layer: target, reason: "用户手动降级" });
      loadEntries();
      if (selectedMemoryId === id) loadDetail(id);
      loadMeta();
    } catch { /* ignore */ }
  };

  const handleArchive = async (id: number) => {
    try {
      await archiveAgentMemory(id, { reason: "用户手动归档" });
      setSelectedMemoryId(null);
      setDetail(null);
      loadEntries();
      loadMeta();
    } catch { /* ignore */ }
  };

  const handleConsolidate = async () => {
    setConsolidating(true);
    try {
      await consolidateAgentMemory(projectId, {
        job_types: ["dedupe", "promote", "expire", "conflict_check"],
      });
      loadEntries();
      loadMeta();
    } catch { /* ignore */ }
    setConsolidating(false);
  };

  return (
    <div className="am-page">
      <AgentSidebar
        projectId={projectId}
        stats={stats}
        agents={agents}
        selectedAgent={selectedAgent}
        onSelectAgent={setSelectedAgent}
      />
      <MemoryBoard
        entries={entries}
        selectedLayer={selectedLayer}
        onSelectLayer={setSelectedLayer}
        selectedMemoryId={selectedMemoryId}
        onSelectMemory={setSelectedMemoryId}
        query={query}
        onQueryChange={setQuery}
        onConsolidate={handleConsolidate}
        consolidating={consolidating}
      />
      <MemoryDetail
        detail={detail}
        onPromote={handlePromote}
        onDemote={handleDemote}
        onArchive={handleArchive}
      />
    </div>
  );
}
