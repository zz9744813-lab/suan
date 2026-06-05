/**
 * PromptMatrixTable — Agent × Genre 矩阵表格 (NF2 阶段1)
 *
 * 从后端 /api/genre-prompts/matrix 获取数据
 * 行: agent_role_keys (包含 reader_* 等读者 Agent)
 * 列: genres
 * 支持 Section 分组 (写作Agent/读者Agent/讨论/记忆/拆书)
 */
import { useCallback, useEffect, useState } from "react";
import { getGenrePromptMatrix, lockPromptCell, unlockPromptCell, getCellRecommendations } from "../../api";
import { PromptCell, type MatrixCell } from "./PromptCell";
import { PromptAutoFillPanel } from "./PromptAutoFillPanel";
import { PromptRecommendationDrawer } from "./PromptRecommendationDrawer";
import { PromptCoverageBar } from "./PromptCoverageBar";

type Section = { key: string; label: string; agents: string[] };

const SECTIONS: Section[] = [
  { key: "writing", label: "写作 Agent", agents: ["planner", "drafter", "critic", "rewriter", "continuity", "memory_update"] },
  { key: "reader", label: "读者 Agent", agents: ["reader_hook", "reader_emotion", "reader_logic", "reader_commercial", "reader_toxic"] },
  { key: "discussion", label: "讨论", agents: ["discussion_chief", "discussion_member"] },
  { key: "memory", label: "记忆", agents: ["memory_manager", "memory_consolidator"] },
  { key: "study", label: "拆书", agents: ["study_extractor", "study_analyzer"] },
];

function normalizeCells(raw: any): { cells: MatrixCell[]; genres: string[]; agent_role_keys: string[] } {
  if (!raw) return { cells: [], genres: [], agent_role_keys: [] };
  const cells: MatrixCell[] = (raw.cells ?? []).map((c: any) => ({
    agent_role_key: c.agent_role_key,
    genre: c.genre,
    template_id: c.prompt_template_id ?? c.template_id ?? null,
    template_name: c.template_name ?? null,
    match_pct: c.match_pct ?? c.match_percent ?? 0,
    state: c.state ?? (c.template_name ? "auto" : "missing"),
    recommendation: c.recommendation ? {
      reason: c.recommendation.reason ?? "",
      historical_effect: c.recommendation.historical_effect ?? undefined,
      overridable: c.recommendation.overridable ?? true,
    } : undefined,
  }));
  return {
    cells,
    genres: raw.genres ?? raw.genre_list ?? [],
    agent_role_keys: raw.agent_role_keys ?? raw.agent_rows ?? [],
  };
}

export function PromptMatrixTable({ projectId }: { projectId?: number }) {
  const [data, setData] = useState<{ cells: MatrixCell[]; genres: string[]; agent_role_keys: string[] }>({ cells: [], genres: [], agent_role_keys: [] });
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState<{ visible: boolean; data: any; cell?: MatrixCell }>({ visible: false, data: null });

  const reload = useCallback(async () => {
    try {
      const raw = await getGenrePromptMatrix();
      setData(normalizeCells(raw));
    } catch { /* */ }
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const getCell = (agentKey: string, genre: string): MatrixCell | undefined =>
    data.cells.find((c) => c.agent_role_key === agentKey && c.genre === genre);

  const filledCount = data.cells.filter((c) => c.state !== "missing").length;
  const totalCount = data.cells.length;

  const handleLock = async (cell: MatrixCell) => {
    try {
      await lockPromptCell(cell.agent_role_key, cell.genre);
      await reload();
    } catch { /* */ }
  };

  const handleUnlock = async (cell: MatrixCell) => {
    try {
      await unlockPromptCell(cell.agent_role_key, cell.genre);
      await reload();
    } catch { /* */ }
  };

  const handleRebind = async (agentKey: string, genre: string) => {
    try {
      const rec = await getCellRecommendations(agentKey, genre);
      setDrawer({
        visible: true,
        data: rec,
        cell: getCell(agentKey, genre),
      });
    } catch { /* */ }
  };

  const handleDrawerApply = async () => {
    setDrawer({ visible: false, data: null });
    await reload();
  };

  const handleDrawerLock = async () => {
    if (drawer.cell) {
      await handleLock(drawer.cell);
    }
    setDrawer({ visible: false, data: null });
  };

  if (loading) return <div style={{ padding: 24 }} className="muted">加载矩阵中…</div>;

  // Merge backend agent_role_keys into sections, add any unknown agents to a catch-all
  const knownAgents = new Set(SECTIONS.flatMap((s) => s.agents));
  const extraAgents = data.agent_role_keys.filter((a) => !knownAgents.has(a));
  const sections = extraAgents.length > 0
    ? [...SECTIONS, { key: "other", label: "其他 Agent", agents: extraAgents }]
    : SECTIONS;

  const genres = data.genres.length > 0 ? data.genres : ["玄幻", "都市", "科幻", "历史", "悬疑", "言情"];

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <PromptCoverageBar filled={filledCount} total={totalCount} />
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {/* Matrix */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {sections.map((sec) => {
            const sectionAgents = sec.agents.filter((a) => data.agent_role_keys.length === 0 || data.agent_role_keys.includes(a));
            if (sectionAgents.length === 0) return null;
            return (
              <div key={sec.key} style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary, #666)", marginBottom: 4, paddingLeft: 4 }}>
                  {sec.label}
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border, #ddd)", minWidth: 100 }}>角色</th>
                      {genres.map((g) => (
                        <th key={g} style={{ padding: "4px 6px", borderBottom: "1px solid var(--border, #ddd)", minWidth: 120, fontSize: 11, textAlign: "center" }}>{g}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sectionAgents.map((ak) => (
                      <tr key={ak}>
                        <td style={{ padding: "4px 8px", fontWeight: 500, whiteSpace: "nowrap", borderBottom: "1px solid var(--border, #eee)" }}>{ak}</td>
                        {genres.map((g) => {
                          const cell = getCell(ak, g) || { agent_role_key: ak, genre: g, template_id: null, template_name: null, match_pct: 0, state: "missing" as const };
                          return (
                            <td key={`${ak}:${g}`} style={{ padding: 2, borderBottom: "1px solid var(--border, #eee)" }}>
                              <PromptCell
                                cell={cell}
                                onLock={() => handleLock(cell)}
                                onUnlock={() => handleUnlock(cell)}
                                onRebind={() => handleRebind(ak, g)}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>

        {/* Auto-fill panel */}
        <div style={{ width: 280, flexShrink: 0 }}>
          <PromptAutoFillPanel onRefresh={reload} />
        </div>
      </div>

      {/* Recommendation drawer */}
      <PromptRecommendationDrawer
        visible={drawer.visible}
        data={drawer.data}
        onClose={() => setDrawer({ visible: false, data: null })}
        onApply={handleDrawerApply}
        onLock={handleDrawerLock}
      />
    </div>
  );
}
