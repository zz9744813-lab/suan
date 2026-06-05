/**
 * ReaderAgentDetailPage — 单个读者的完整编辑页 (NF2 阶段3)
 *
 * 编辑: 启用/禁用, 显示名, 维度说明, 权重
 * 查看: 最近20条评论, 采纳/驳回统计, 模型绑定, Prompt绑定
 */
import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageTopbar } from "../components/layout/PageTopbar";
import {
  getReaderAgent, updateReaderAgent,
  getReaderComments, getReaderStats,
} from "../api";

export function ReaderAgentDetailPage() {
  const { readerKey } = useParams<{ readerKey: string }>();
  const navigate = useNavigate();
  const [reader, setReader] = useState<any>(null);
  const [comments, setComments] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ display_name: "", dimension: "", weight: 1, enabled: true });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!readerKey) return;
    try {
      const [r, c, s] = await Promise.all([
        getReaderAgent(readerKey),
        getReaderComments(readerKey, 20),
        getReaderStats(readerKey),
      ]);
      setReader(r);
      setComments(Array.isArray(c) ? c : []);
      setStats(s);
      setForm({
        display_name: r.display_name ?? "",
        dimension: r.dimension ?? "",
        weight: r.weight ?? 1,
        enabled: r.enabled !== false,
      });
    } catch { /* */ }
  }, [readerKey]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    if (!readerKey) return;
    setSaving(true);
    try {
      await updateReaderAgent(readerKey, form);
      setEditing(false);
      await load();
    } catch (e: any) {
      alert(e.message || "保存失败");
    }
    setSaving(false);
  };

  if (!reader) return <div className="muted" style={{ padding: 24 }}>加载中…</div>;

  return (
    <div>
      <PageTopbar
        title={reader.display_name || readerKey || ""}
        icon="📖"
        subtitle={`${readerKey} · ${reader.dimension || ""}`}
        actions={[
          { label: "返回列表", variant: "ghost", onClick: () => navigate("/reader-agents") },
          {
            label: editing ? "取消编辑" : "编辑",
            variant: editing ? "ghost" : "primary",
            onClick: () => setEditing(!editing),
          },
        ]}
      />

      <div style={{ padding: "16px 24px", display: "flex", gap: 16 }}>
        {/* Left: edit form */}
        <div style={{ flex: 1 }}>
          <div style={{ padding: 16, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 15 }}>基本信息</h3>

            {editing ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ fontSize: 12 }}>
                  显示名
                  <input
                    className="input"
                    style={{ width: "100%", marginTop: 2 }}
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  维度说明
                  <input
                    className="input"
                    style={{ width: "100%", marginTop: 2 }}
                    value={form.dimension}
                    onChange={(e) => setForm({ ...form, dimension: e.target.value })}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  权重
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={10}
                    step={0.1}
                    style={{ width: 80, marginTop: 2 }}
                    value={form.weight}
                    onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })}
                  />
                </label>
                <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                  />
                  启用
                </label>
                <div>
                  <button className="primary" onClick={handleSave} disabled={saving}>
                    {saving ? "保存中..." : "保存"}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>显示名</div>
                  <div>{reader.display_name}</div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>维度</div>
                  <div>{reader.dimension}</div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>权重</div>
                  <div>{reader.weight ?? "—"}</div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>启用</div>
                  <span
                    className="pill"
                    style={{
                      fontSize: 10,
                      background: reader.enabled !== false ? "#e8f5e9" : "#fafafa",
                      color: reader.enabled !== false ? "#2e7d32" : "#9e9e9e",
                    }}
                  >
                    {reader.enabled !== false ? "启用" : "禁用"}
                  </span>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>模型绑定</div>
                  <div>{reader.model_binding ?? "未绑定"}</div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>Prompt绑定</div>
                  <div>{reader.prompt_binding ?? "未绑定"}</div>
                </div>
              </div>
            )}
          </div>

          {/* Stats */}
          {stats && (
            <div style={{ marginTop: 16, padding: 16, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
              <h3 style={{ margin: "0 0 12px", fontSize: 15 }}>评审统计</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                <StatBlock label="总评论" value={stats.total_count ?? comments.length} />
                <StatBlock label="采纳数" value={stats.adopted_count ?? 0} />
                <StatBlock label="驳回数" value={stats.rejected_count ?? 0} />
              </div>
            </div>
          )}
        </div>

        {/* Right: recent comments */}
        <div style={{ width: 420, flexShrink: 0 }}>
          <div style={{ padding: 16, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 15 }}>最近评论</h3>
            {comments.length === 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>暂无评论</div>
            ) : (
              <div style={{ maxHeight: 500, overflow: "auto" }}>
                {comments.map((c, i) => (
                  <div
                    key={c.id ?? i}
                    style={{
                      padding: "8px 0",
                      borderBottom: "1px solid var(--border, #eee)",
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                      <span style={{ fontWeight: 500 }}>{c.title || c.comment_type || `评论#${i + 1}`}</span>
                      <span
                        className="pill"
                        style={{
                          fontSize: 10,
                          background: c.severity === "high" ? "#fce4ec" : c.severity === "medium" ? "#fff3e0" : "#e8f5e9",
                          color: c.severity === "high" ? "#c62828" : c.severity === "medium" ? "#e65100" : "#2e7d32",
                        }}
                      >
                        {c.severity || "info"}
                      </span>
                    </div>
                    <div className="muted" style={{ marginBottom: 2 }}>
                      {c.content?.slice(0, 120) || ""}
                    </div>
                    {c.evidence && (
                      <div className="muted" style={{ fontSize: 11, fontStyle: "italic" }}>
                        证据: {typeof c.evidence === "string" ? c.evidence.slice(0, 80) : JSON.stringify(c.evidence).slice(0, 80)}
                      </div>
                    )}
                    <div className="muted" style={{ fontSize: 10 }}>
                      {c.created_at ? new Date(c.created_at).toLocaleString("zh-CN") : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatBlock({ label, value }: { label: string; value: any }) {
  return (
    <div style={{ padding: 10, borderRadius: 4, background: "var(--bg-surface, #f5f5f5)" }}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{String(value)}</div>
    </div>
  );
}
