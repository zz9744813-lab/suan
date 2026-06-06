/* AddBookModal — 书架内置"加书"弹窗 (P0-1)
 *
 * 两个 Tab:
 *   1. 文件上传 — 拖拽/点击, 支持 txt/md/pdf/docx/html/epub, 最多 5 本
 *   2. 粘贴正文 — 标题+作者+分类+标签+正文, 保存并自动拆书
 *
 * 上传后自动分章 + 自动创建 DeepStudy run, 书架直接刷新.
 */
import { useState, useRef } from "react";
import {
  uploadStudyMaterialsBatch,
  createStudyMaterialFromText,
} from "../../api";
import "./AddBookModal.css";

const MAX_BATCH_FILES = 5;
const ACCEPTED_FORMATS = ".txt,.md,.markdown,.pdf,.docx,.html,.htm,.epub";

const CATEGORIES = [
  "未分组",
  "玄幻",
  "都市",
  "历史",
  "科幻",
  "言情",
  "武侠",
  "同人",
  "古典",
  "其他",
];

type Tab = "upload" | "paste";
type UploadResult = {
  ok: { id: number; title: string }[];
  failed: { filename?: string; error: string }[];
};

interface Props {
  onClose: () => void;
  onCreated: (bookId: number) => void;
}

export function AddBookModal({ onClose, onCreated }: Props) {
  const [tab, setTab] = useState<Tab>("upload");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);

  // Upload tab state
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Paste tab state
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteAuthor, setPasteAuthor] = useState("");
  const [pasteCategory, setPasteCategory] = useState("未分组");
  const [pasteTagsText, setPasteTagsText] = useState("");
  const [pasteText, setPasteText] = useState("");

  // Shared category + tags for upload tab
  const [uploadCategory, setUploadCategory] = useState("未分组");
  const [uploadTagsText, setUploadTagsText] = useState("");

  // ---- Upload logic ----
  async function uploadFiles(files: File[]) {
    if (!files.length) return;
    const limited = files.slice(0, MAX_BATCH_FILES);
    const fd = new FormData();
    for (const f of limited) {
      fd.append("files", f);
    }
    // Attach category + tags
    if (uploadCategory && uploadCategory !== "未分组") {
      fd.append("shelf_category", uploadCategory);
    }
    const tags = uploadTagsText
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (tags.length > 0) {
      fd.append("tags_json", JSON.stringify(tags));
    }

    setBusy(true);
    setError(null);
    setUploadResult(null);
    try {
      const results = await uploadStudyMaterialsBatch(fd);
      const ok = results
        .filter((r): r is { ok: true; data: any } => r.ok)
        .map((r) => ({ id: r.data.id, title: r.data.title }));
      const failed = results
        .filter((r): r is { ok: false; filename?: string; error: string } => !r.ok)
        .map((r) => ({ filename: r.filename, error: r.error }));
      setUploadResult({ ok, failed });
      if (ok.length > 0) {
        onCreated(ok[0].id);
      }
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  // ---- Paste logic ----
  async function createFromText() {
    if (!pasteTitle.trim() || !pasteText.trim()) {
      setError("标题和正文不能为空。");
      return;
    }
    const tags = pasteTagsText
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    setBusy(true);
    setError(null);
    try {
      const book: any = await createStudyMaterialFromText({
        title: pasteTitle.trim(),
        author: pasteAuthor.trim() || undefined,
        raw_text: pasteText,
        shelf_category: pasteCategory || undefined,
        tags: tags.length > 0 ? tags : undefined,
        auto_chapterize: true,
        auto_deepstudy: true,
      });
      onCreated(book.id);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  // ---- Render ----
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="add-book-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>+ 加书</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-tabs">
          <button
            className={`modal-tab ${tab === "upload" ? "active" : ""}`}
            onClick={() => setTab("upload")}
          >
            文件上传
          </button>
          <button
            className={`modal-tab ${tab === "paste" ? "active" : ""}`}
            onClick={() => setTab("paste")}
          >
            粘贴正文
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="modal-error">{error}</div>}

          {tab === "upload" && (
            <div className="upload-tab">
              <div
                className={`drop-zone ${dragging ? "dragging" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  uploadFiles(Array.from(e.dataTransfer.files ?? []));
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="drop-zone-icon">📄</div>
                <div>拖拽文件到这里，或点击选择</div>
                <div className="drop-zone-hint">
                  支持 txt / md / pdf / docx / html / epub，最多 {MAX_BATCH_FILES} 本
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_FORMATS}
                multiple
                style={{ display: "none" }}
                onChange={(e) => {
                  const files = e.target.files ? Array.from(e.target.files) : [];
                  if (files.length > 0) uploadFiles(files);
                }}
              />

              {/* Category + tags for upload */}
              <div className="form-row">
                <label>分类</label>
                <select value={uploadCategory} onChange={(e) => setUploadCategory(e.target.value)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="form-row">
                <label>标签</label>
                <input
                  className="input"
                  placeholder="逗号或空格分隔，如: 智斗, 反派, 修真"
                  value={uploadTagsText}
                  onChange={(e) => setUploadTagsText(e.target.value)}
                />
              </div>

              {/* Upload results */}
              {uploadResult && (
                <div className="upload-results">
                  {uploadResult.ok.length > 0 && (
                    <div className="upload-success">
                      <div className="upload-result-title">成功上传 {uploadResult.ok.length} 本:</div>
                      {uploadResult.ok.map((b) => (
                        <div key={b.id} className="upload-result-item ok">
                          {b.title}
                        </div>
                      ))}
                    </div>
                  )}
                  {uploadResult.failed.length > 0 && (
                    <div className="upload-failed">
                      <div className="upload-result-title">失败 {uploadResult.failed.length} 个:</div>
                      {uploadResult.failed.map((f, i) => (
                        <div key={i} className="upload-result-item failed">
                          {f.filename ?? "未知文件"}: {f.error}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {busy && <div className="modal-loading">上传中…</div>}
            </div>
          )}

          {tab === "paste" && (
            <div className="paste-tab">
              <div className="form-row">
                <label>标题 *</label>
                <input
                  className="input"
                  placeholder="书名"
                  value={pasteTitle}
                  onChange={(e) => setPasteTitle(e.target.value)}
                />
              </div>
              <div className="form-row-inline">
                <div className="form-row half">
                  <label>作者</label>
                  <input
                    className="input"
                    placeholder="作者名"
                    value={pasteAuthor}
                    onChange={(e) => setPasteAuthor(e.target.value)}
                  />
                </div>
                <div className="form-row half">
                  <label>分类</label>
                  <select value={pasteCategory} onChange={(e) => setPasteCategory(e.target.value)}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-row">
                <label>标签</label>
                <input
                  className="input"
                  placeholder="逗号或空格分隔，如: 智斗, 反派, 修真"
                  value={pasteTagsText}
                  onChange={(e) => setPasteTagsText(e.target.value)}
                />
              </div>
              <div className="form-row grow">
                <label>正文 *</label>
                <textarea
                  className="input textarea"
                  placeholder="粘贴小说正文…"
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  rows={12}
                />
              </div>
              <div className="form-actions">
                <button className="btn secondary" onClick={onClose} disabled={busy}>
                  取消
                </button>
                <button
                  className="btn primary"
                  onClick={createFromText}
                  disabled={busy || !pasteTitle.trim() || !pasteText.trim()}
                >
                  {busy ? "保存并拆书中…" : "保存并自动拆书"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
