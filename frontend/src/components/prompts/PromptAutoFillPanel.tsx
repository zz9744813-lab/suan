/**
 * PromptAutoFillPanel — 自动填充操作面板 (NF2 阶段1)
 *
 * 按钮: "预览自动填充" / "应用高置信推荐" / "只补空白格" / "回滚上次填充"
 * 显示覆盖率进度条
 * 调用 prompt_matrix 相关 API
 */
import { useState } from "react";
import {
  previewPromptAutoFill, applyPromptAutoFill,
  rollbackPromptAutoFill, getPromptMatrixCoverage,
} from "../../api";
import { PromptCoverageBar } from "./PromptCoverageBar";
import { PromptBatchHistory } from "./PromptBatchHistory";

export function PromptAutoFillPanel({ onRefresh }: { onRefresh: () => void }) {
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [coverage, setCoverage] = useState<{ filled: number; total: number } | null>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refreshCoverage = async () => {
    try {
      const c = await getPromptMatrixCoverage();
      setCoverage({ filled: c.filled ?? c.covered ?? 0, total: c.total ?? 0 });
    } catch { /* */ }
  };

  const handlePreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await previewPromptAutoFill({});
      setPreview(r);
      setBatches(r.batches ?? []);
    } catch (e: any) {
      setError(e.message || "预览失败");
    }
    setLoading(false);
  };

  const handleApplyHigh = async () => {
    if (!preview?.batch_key) { setError("请先预览"); return; }
    setLoading(true);
    try {
      await applyPromptAutoFill({ batch_key: preview.batch_key, apply_confidence: ["high"] });
      setPreview(null);
      await refreshCoverage();
      onRefresh();
    } catch (e: any) {
      setError(e.message || "应用失败");
    }
    setLoading(false);
  };

  const handleFillEmpty = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await previewPromptAutoFill({ scope: "empty_only" });
      if (r.batch_key) {
        await applyPromptAutoFill({ batch_key: r.batch_key });
      }
      setPreview(null);
      await refreshCoverage();
      onRefresh();
    } catch (e: any) {
      setError(e.message || "填充失败");
    }
    setLoading(false);
  };

  const handleRollback = async (batchKey: string) => {
    setLoading(true);
    try {
      await rollbackPromptAutoFill(batchKey);
      setBatches((prev) => prev.map((b) => b.batch_key === batchKey ? { ...b, status: "rolled_back" } : b));
      await refreshCoverage();
      onRefresh();
    } catch (e: any) {
      setError(e.message || "回滚失败");
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: 12, border: "1px solid var(--border, #ddd)", borderRadius: 6 }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>自动填充</div>

      {coverage && <PromptCoverageBar filled={coverage.filled} total={coverage.total} />}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
        <button className="small" onClick={handlePreview} disabled={loading}>
          {loading ? "处理中..." : "预览自动填充"}
        </button>
        <button className="small primary" onClick={handleApplyHigh} disabled={loading || !preview}>
          应用高置信推荐
        </button>
        <button className="small" onClick={handleFillEmpty} disabled={loading}>
          只补空白格
        </button>
      </div>

      {error && <div style={{ color: "#c62828", fontSize: 12, marginTop: 6 }}>{error}</div>}

      {preview && (
        <div style={{ marginTop: 10, fontSize: 12 }}>
          <div>预览: {preview.fill_count ?? 0} 个格子将被填充</div>
          {preview.batch_key && <div className="muted">Batch: {preview.batch_key}</div>}
        </div>
      )}

      <div style={{ marginTop: 10 }}>
        <PromptBatchHistory batches={batches} onRollback={handleRollback} />
      </div>
    </div>
  );
}
