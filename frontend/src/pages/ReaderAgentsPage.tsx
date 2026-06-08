/**
 * ReaderAgentsPage — 5读者Agent编辑中心 (NF2 阶段3)
 *
 * 左侧: 5 个读者 Agent 卡片列表
 * 右侧: 选中读者的详情
 * 顶部: PageTopbar "读者Agent编辑中心"
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageTopbar } from "../components/layout/PageTopbar";
import { listReaderAgents, getReaderStats } from "../api";

const DEFAULT_READERS = [
  { reader_key: "reader_hook", display_name: "Reader·钩子", dimension: "悬念/钩子/留白" },
  { reader_key: "reader_emotion", display_name: "Reader·情绪", dimension: "情感/共鸣/代入" },
  { reader_key: "reader_logic", display_name: "Reader·逻辑", dimension: "逻辑/因果/设定" },
  { reader_key: "reader_commercial", display_name: "Reader·商业", dimension: "市场/留存/付费" },
  { reader_key: "reader_toxic", display_name: "Reader·毒点", dimension: "劝退/违和/解释腔" },
];

export function ReaderAgentsPage() {
  const [readers, setReaders] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, any>>({});
  const navigate = useNavigate();

  useEffect(() => {
    listReaderAgents()
      .then((r) => {
        const list = Array.isArray(r) ? r : (r as any).items ?? DEFAULT_READERS;
        setReaders(list);
        if (list.length > 0 && !selected) setSelected(list[0].reader_key);
      })
      .catch(() => setReaders(DEFAULT_READERS));
  }, []);

  useEffect(() => {
    if (!selected) return;
    getReaderStats(selected)
      .then((s) => setStats((prev) => ({ ...prev, [selected]: s })))
      .catch(() => {});
  }, [selected]);

  const current = readers.find((r) => r.reader_key === selected);
  const currentStats = selected ? stats[selected] : null;

  return (
    <div>
      <PageTopbar
        title="读者Agent编辑中心"
        icon="📖"
        subtitle="5位模拟读者 Agent 的配置与评审统计"
        actions={[
          {
            label: "全量刷新",
            variant: "ghost",
            onClick: () => window.location.reload(),
          },
        ]}
      />

      <div style={{ display: "flex", gap: 16, padding: "16px 24px" }}>
        {/* Left: reader cards */}
        <div style={{ width: 280, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {readers.map((r) => {
            const s = stats[r.reader_key];
            const isActive = selected === r.reader_key;
            return (
              <div
                key={r.reader_key}
                onClick={() => setSelected(r.reader_key)}
                style={{
                  padding: 12,
                  borderRadius: 6,
                  border: `1px solid ${isActive ? "var(--accent, #4f46e5)" : "var(--border, #ddd)"}`,
                  background: isActive ? "var(--bg-hover, #f0f0ff)" : "var(--bg-card, #fff)",
                  cursor: "pointer",
                  transition: "border-color 0.15s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{r.display_name}</span>
                  <span
                    className="pill"
                    style={{
                      fontSize: 10,
                      background: r.enabled !== false ? "#e8f5e9" : "#fafafa",
                      color: r.enabled !== false ? "#2e7d32" : "#9e9e9e",
                    }}
                  >
                    {r.enabled !== false ? "启用" : "禁用"}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>
                  {r.reader_key}
                </div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
                  维度: {r.dimension}
                </div>
                {s && (
                  <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
                    <span>采纳: {s.adopted_count ?? 0}</span>
                    <span>驳回: {s.rejected_count ?? 0}</span>
                    {r.weight != null && <span>权重: {r.weight}</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right: detail */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {current ? (
            <div style={{ padding: 16, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: 18 }}>{current.display_name}</h2>
                  <div className="muted" style={{ fontSize: 12 }}>{current.reader_key} · {current.dimension}</div>
                </div>
                <button
                  className="primary"
                  onClick={() => navigate(`/reader-agents/${current.reader_key}`)}
                >
                  编辑详情
                </button>
              </div>

              {/* Stats grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
                <StatCard label="启用状态" value={current.enabled !== false ? "启用" : "禁用"} />
                <StatCard label="权重" value={current.weight ?? "—"} />
                <StatCard label="采纳数" value={currentStats?.adopted_count ?? 0} />
                <StatCard label="驳回数" value={currentStats?.rejected_count ?? 0} />
              </div>

              {/* Model & Prompt binding */}
              <div style={{ fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div style={{ fontWeight: 600 }}>模型与提示词</div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="ghost" onClick={() => navigate("/models")}>配置模型</button>
                    <button className="ghost" onClick={() => navigate("/prompts")}>配置提示词</button>
                  </div>
                </div>
                <div className="muted" style={{ marginBottom: 4 }}>
                  模型: {formatModelBinding(current)}
                </div>
                <div className="muted" style={{ marginBottom: 4 }}>
                  系统提示词: {current.system_prompt_template_name ?? current.system_prompt_template_key ?? "未绑定"}
                </div>
                <div className="muted">
                  任务提示词: {current.task_prompt_template_name ?? current.task_prompt_template_key ?? "未绑定"}
                </div>
              </div>
            </div>
          ) : (
            <div className="muted" style={{ padding: 24, textAlign: "center" }}>选择左侧读者查看详情</div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatModelBinding(reader: any) {
  if (!reader) return "未绑定";
  const provider = reader.provider_name ?? (reader.provider_id ? `Provider #${reader.provider_id}` : null);
  const model = reader.model_name;
  if (provider && model) return `${provider} / ${model}`;
  if (model) return model;
  if (provider) return provider;
  return "未绑定";
}

function StatCard({ label, value }: { label: string; value: any }) {
  return (
    <div style={{ padding: 10, borderRadius: 4, background: "var(--bg-surface, #f5f5f5)" }}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600 }}>{String(value)}</div>
    </div>
  );
}
