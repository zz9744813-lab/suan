/**
 * FirstRunGuide — 首次运行引导弹窗
 *
 * 当 ModelsPage 检测到只有 stub Provider (mock 模式) 时弹出,
 * 引导用户快速添加真实的外部 API Provider.
 */
import React from "react";

type FirstRunGuideProps = {
  open: boolean;
  onClose: () => void;
  onCreateProvider: (type: string) => void;
};

export function FirstRunGuide({ open, onClose, onCreateProvider }: FirstRunGuideProps) {
  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal first-run-guide-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ width: 520 }}
      >
        <div className="modal-head">
          <h3 className="serif">👋 欢迎使用 NovelForge 模型配置</h3>
          <button onClick={onClose} className="modal-close">✕</button>
        </div>

        <div className="modal-body" style={{ textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.7, marginBottom: 20 }}>
            当前系统使用 mock 模式运行，仅用于开发测试。要开始真实写作，请添加至少一个外部 API Provider。
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
            <button
              className="primary"
              style={{ padding: "12px 16px", fontSize: 14 }}
              onClick={() => onCreateProvider("openrouter")}
            >
              ⚡ 快速添加 OpenRouter
            </button>
            <button
              className="primary"
              style={{ padding: "12px 16px", fontSize: 14 }}
              onClick={() => onCreateProvider("deepseek")}
            >
              ⚡ 快速添加 DeepSeek
            </button>
            <button
              style={{ padding: "12px 16px", fontSize: 14 }}
              onClick={() => onCreateProvider("custom")}
            >
              🔧 手动配置 Provider
            </button>
          </div>

          <p style={{ color: "var(--text-muted)", fontSize: 12, lineHeight: 1.6, marginTop: 12 }}>
            推荐 OpenRouter — 支持 Claude、GPT-4o、Gemini 等 200+ 模型，一个 API Key 搞定
          </p>
        </div>
      </div>
    </div>
  );
}
