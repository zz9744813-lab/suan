/**
 * CoverageTracePanel — 模板覆盖率 + 使用追溯 (P0 返工 Phase 2.3+2.4)
 *
 *   - 覆盖率: GET /api/prompts/coverage → role × genre 矩阵
 *   - 使用追溯: GET /api/prompts/usage → top 模板 + 单模板最近 run
 */
import { useEffect, useState } from "react";
import { getPromptCoverage, getPromptUsage } from "../../api";
import type { PromptCoverage, PromptUsageTop, PromptUsageRun } from "../../types";

type View = "coverage" | "usage" | "trace";

export function CoverageTracePanel() {
  const [view, setView] = useState<View>("coverage");
  const [coverage, setCoverage] = useState<PromptCoverage | null>(null);
  const [topUsage, setTopUsage] = useState<PromptUsageTop | null>(null);
  const [selectedTpl, setSelectedTpl] = useState<number | null>(null);
  const [singleUsage, setSingleUsage] = useState<PromptUsageTop | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getPromptCoverage()
      .then((c) => setCoverage(c))
      .catch((e) => setErr(String(e?.message ?? e)));
    getPromptUsage(undefined, 50)
      .then((u) => setTopUsage(u))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedTpl != null) {
      getPromptUsage(selectedTpl, 30)
        .then(setSingleUsage)
        .catch(() => setSingleUsage(null));
    } else {
      setSingleUsage(null);
    }
  }, [selectedTpl]);

  if (err) {
    return <div className="coverage-trace-panel error">加载失败：{err}</div>;
  }
  if (!coverage) {
    return <div className="coverage-trace-panel muted small">加载中…</div>;
  }

  return (
    <section className="coverage-trace-panel">
      <div className="coverage-trace-header">
        <div className="coverage-trace-tabs">
          <button
            className={view === "coverage" ? "active" : ""}
            onClick={() => setView("coverage")}
          >
            📊 覆盖率
          </button>
          <button
            className={view === "usage" ? "active" : ""}
            onClick={() => setView("usage")}
          >
            🔥 使用排行
          </button>
          <button
            className={view === "trace" ? "active" : ""}
            onClick={() => setView("trace")}
            disabled={selectedTpl == null}
          >
            🔍 单模板追溯 {selectedTpl != null ? `#${selectedTpl}` : ""}
          </button>
        </div>
        <div className="coverage-trace-summary">
          <span className="big">{coverage.summary.coverage_pct}%</span>
          <span className="muted small">
            {coverage.summary.covered_cells} / {coverage.summary.total_cells} 单元已覆盖
            {coverage.summary.missing_cells > 0 && ` · 缺 ${coverage.summary.missing_cells}`}
          </span>
        </div>
      </div>

      {view === "coverage" && (
        <div className="coverage-matrix-wrap">
          <table className="coverage-matrix">
            <thead>
              <tr>
                <th>Agent / 角色</th>
                {coverage.genres.map((g) => (
                  <th key={g}>{g}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {coverage.rows.map((row) => (
                <tr key={row.role_key}>
                  <th className={`cov-row cov-${row.category}`}>
                    <span className="cov-row-label">{row.role_label}</span>
                    <span className="cov-row-key muted tiny">{row.role_key}</span>
                  </th>
                  {coverage.genres.map((g) => {
                    const cell = coverage.cells[`${row.role_key}:${g}`];
                    const ok = cell === 1;
                    return (
                      <td key={g} className={ok ? "cov-ok" : "cov-empty"}>
                        {ok ? "✓" : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="coverage-legend muted small">
            ✓ = 有模板 · — = 空缺 · 全局模板 (genre=NULL) 对所有流派都算通配覆盖
          </div>
        </div>
      )}

      {view === "usage" && (
        <div className="usage-top-wrap">
          {!topUsage?.top_templates?.length ? (
            <div className="muted small" style={{ padding: 16 }}>
              还没有任何 AgentRun 记录了 prompt_template_id。
              <br />
              跑一次 worker 后刷新此页。
            </div>
          ) : (
            <table className="usage-top-table">
              <thead>
                <tr>
                  <th>模板</th>
                  <th>角色</th>
                  <th>类别</th>
                  <th>流派</th>
                  <th>使用次数</th>
                  <th>总 Token</th>
                  <th>总成本</th>
                  <th>追溯</th>
                </tr>
              </thead>
              <tbody>
                {topUsage.top_templates.map((t) => (
                  <tr key={t.template_id}>
                    <td>
                      <div>{t.name ?? "—"}</div>
                      <div className="muted tiny">{t.template_key}</div>
                    </td>
                    <td>{t.role}</td>
                    <td>{t.category}</td>
                    <td>{t.genre ?? "—"}</td>
                    <td><strong>{t.usage_count}</strong></td>
                    <td>{t.total_tokens.toLocaleString()}</td>
                    <td>${t.total_cost.toFixed(4)}</td>
                    <td>
                      <button
                        className="small"
                        onClick={() => { setSelectedTpl(t.template_id); setView("trace"); }}
                      >
                        查看 →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {view === "trace" && (
        <div className="trace-wrap">
          {!singleUsage?.runs?.length ? (
            <div className="muted small" style={{ padding: 16 }}>
              模板 #{selectedTpl} 还没有任何 run 记录。
            </div>
          ) : (
            <table className="trace-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>状态</th>
                  <th>模型</th>
                  <th>Token in/out</th>
                  <th>成本</th>
                  <th>耗时</th>
                  <th>开始</th>
                </tr>
              </thead>
              <tbody>
                {singleUsage.runs.map((r: PromptUsageRun) => (
                  <tr key={r.id}>
                    <td>#{r.id}</td>
                    <td><span className={`pill tiny ${r.status}`}>{r.status}</span></td>
                    <td>{r.model_name ?? "—"}</td>
                    <td>{r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}</td>
                    <td>${r.cost_usd.toFixed(4)}</td>
                    <td>{r.elapsed_ms ? `${r.elapsed_ms}ms` : "—"}</td>
                    <td className="muted tiny">{r.started_at?.slice(0, 19) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
