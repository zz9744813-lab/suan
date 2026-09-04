/**
 * 影像相学面板：面相/掌纹上传分析。
 *
 * 隐私铁律（与后端 app/services/imaging.py 对齐）：
 * - 默认本地 OpenCV 分析，原图分析后即焚、不入库；
 * - 「云端详批」每一次都要显式勾选，勾选=当次授权把原图发给中转站模型；
 * - 预览用 URL.createObjectURL，仅用 data/blob 本地 URL，不上传预览本身。
 */

import { useRef, useState } from 'react';

import { api, type ImagingAnalysis } from '../api/client';
import { Badge, ErrorBox, GhostButton, PrimaryButton } from './ui';

type Kind = 'palm' | 'face';

const KIND_META: Record<
  Kind,
  { title: string; glyph: string; hint: string }
> = {
  face: {
    title: '面相 · 三庭五眼',
    glyph: '面',
    hint: '正脸免冠、五官无遮挡、光线均匀',
  },
  palm: {
    title: '掌纹 · 三大主线',
    glyph: '掌',
    hint: '掌心朝上摊平、五指自然分开',
  },
};

interface SlotState {
  file: File | null;
  preview: string | null;
  busy: boolean;
  dragOver: boolean;
  useCloud: boolean;
  result: ImagingAnalysis | null;
  error: string | null;
}

const EMPTY: SlotState = {
  file: null,
  preview: null,
  busy: false,
  dragOver: false,
  useCloud: false,
  result: null,
  error: null,
};

function KindSlot({ kind }: { kind: Kind }) {
  const meta = KIND_META[kind];
  const [s, setS] = useState<SlotState>(EMPTY);
  const inputRef = useRef<HTMLInputElement>(null);

  const set = (patch: Partial<SlotState>) => setS((prev) => ({ ...prev, ...patch }));

  const pick = (f: File | null) => {
    if (s.preview) URL.revokeObjectURL(s.preview);
    if (!f) {
      set({ file: null, preview: null, result: null, error: null });
      return;
    }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) {
      set({ error: '仅支持 JPEG / PNG / WebP 图片' });
      return;
    }
    if (f.size > 8 * 1024 * 1024) {
      set({ error: '图片不能超过 8MB' });
      return;
    }
    set({
      file: f,
      preview: URL.createObjectURL(f),
      result: null,
      error: null,
    });
  };

  const analyze = async () => {
    if (!s.file) return;
    set({ busy: true, error: null });
    try {
      const form = new FormData();
      form.append('file', s.file);
      form.append('kind', kind);
      form.append('use_cloud', String(s.useCloud));
      const result = await api.imagingAnalyze(form);
      set({ result, busy: false });
    } catch (e) {
      set({ busy: false, error: e instanceof Error ? e.message : '分析失败' });
    }
  };

  return (
    <div className="rounded-xl border border-bd bg-panel/60 p-3.5">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="text-xs font-medium text-t1">{meta.title}</div>
        <Badge tone="gilt">本地 CV</Badge>
      </div>

      {/* 拖放/点击上传区 */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          set({ dragOver: true });
        }}
        onDragLeave={() => set({ dragOver: false })}
        onDrop={(e) => {
          e.preventDefault();
          set({ dragOver: false });
          pick(e.dataTransfer.files?.[0] ?? null);
        }}
        className={`relative flex h-36 cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-dashed transition-all duration-200 ${
          s.dragOver
            ? 'border-gilt-400 bg-gilt-500/10 shadow-[0_0_18px_-4px_rgba(201,162,39,0.5)]'
            : 'border-bd bg-card/50 hover:border-gilt-500/50 hover:bg-gilt-500/[0.04]'
        }`}
      >
        {s.preview ? (
          <img
            src={s.preview}
            alt="待分析照片预览（仅本地预览，不上传预览图）"
            className="h-full w-full object-cover opacity-90"
          />
        ) : (
          <div className="flex flex-col items-center gap-1.5 text-center">
            <span className="text-gilt-grad font-serif text-2xl">{meta.glyph}</span>
            <span className="text-xs text-t3">点击选择或拖入照片</span>
            <span className="text-[10px] text-t5">{meta.hint}</span>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
      </div>

      {/* 隐私声明 + 云端开关 */}
      <div className="mt-2.5 space-y-1.5">
        <div className="flex flex-wrap gap-1">
          <Badge tone="good">原图分析后即焚</Badge>
          <Badge>结果不入库</Badge>
        </div>
        <label className="flex cursor-pointer items-start gap-2 text-[11px] leading-relaxed text-t3">
          <input
            type="checkbox"
            checked={s.useCloud}
            onChange={(e) => set({ useCloud: e.target.checked })}
            className="mt-0.5 accent-[#c9a227]"
          />
          <span>
            云端详批（可选）：勾选后<strong className="text-t2">原图会发送到第三方模型服务</strong>
            （agnes-2.5-flash）生成一段相学口径的参考解读；不勾选则纯本地分析。
          </span>
        </label>
      </div>

      <div className="mt-2.5 flex items-center gap-2">
        <PrimaryButton onClick={analyze} busy={s.busy} disabled={!s.file} className="text-xs">
          {s.busy ? '分析中…' : '开始分析'}
        </PrimaryButton>
        {s.file && (
          <GhostButton onClick={() => pick(null)} disabled={s.busy}>
            清除
          </GhostButton>
        )}
      </div>

      {s.error && <div className="mt-2"><ErrorBox message={s.error} /></div>}

      {s.result && (
        <div className="animate-fade-up mt-3 space-y-2 border-t border-bd pt-3">
          {!s.result.detected && (
            <Badge tone="warn">未检测到{kind === 'palm' ? '手部' : '人脸'}</Badge>
          )}
          <ul className="space-y-1">
            {s.result.reading.map((line, i) => (
              <li key={i} className="flex gap-1.5 text-xs leading-relaxed text-t2">
                <span className="text-gt">·</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>

          {s.result.cloud.used && s.result.cloud.text && (
            <div className="rounded-lg border border-gilt-500/30 bg-gilt-500/[0.06] p-2.5">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] text-t4">
                <Badge tone="gilt">云端详批 · {s.result.cloud.model}</Badge>
                <span>{s.result.cloud.duration_ms}ms</span>
              </div>
              <p className="text-xs leading-relaxed text-t2">{s.result.cloud.text}</p>
            </div>
          )}
          {s.useCloud && !s.result.cloud.used && s.result.cloud.reason && (
            <p className="text-[11px] text-t4">云端详批未执行：{s.result.cloud.reason}</p>
          )}

          <details className="text-[11px] text-t4">
            <summary className="cursor-pointer select-none hover:text-t2">
              测量特征（数值）
            </summary>
            <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-panel p-2 font-mono text-[10px] leading-relaxed text-t4">
              {JSON.stringify(s.result.features, null, 2)}
            </pre>
          </details>

          <p className="text-[10px] leading-relaxed text-t5">{s.result.privacy.note}</p>
        </div>
      )}
    </div>
  );
}

export function ImagingPanel() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <KindSlot kind="face" />
      <KindSlot kind="palm" />
    </div>
  );
}
