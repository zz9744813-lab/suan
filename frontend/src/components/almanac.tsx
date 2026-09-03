import { useMemo } from 'react';
import type { CSSProperties } from 'react';

/**
 * 玄学视觉组件：罗盘（AlmanacDial）+ 幸运色色卡（ColorSwatches）+ 域色主题（DOMAIN_ACCENT）。
 * 全部纯 SVG/CSS，无外部资源；动效已接入 prefers-reduced-motion（见 index.css）。
 */

/** 方位归一：把「西北 / 正东 / 东南方」这类文本映射到八向角度（北=0°，顺时针） */
const DIRECTION_DEG: Record<string, number> = {
  北: 0, 东北: 45, 东: 90, 东南: 135, 南: 180, 西南: 225, 西: 270, 西北: 315,
};

function dirToDeg(text: string | undefined): number | null {
  if (!text) return null;
  const t = text.replace(/正|方|位/g, '');
  return DIRECTION_DEG[t] ?? null;
}

/** 后天八卦方位（北=坎 … 西北=乾），罗盘外环随方位排布 */
const TRIGRAMS: { deg: number; glyph: string; name: string }[] = [
  { deg: 0, glyph: '☵', name: '坎' },
  { deg: 45, glyph: '☶', name: '艮' },
  { deg: 90, glyph: '☳', name: '震' },
  { deg: 135, glyph: '☴', name: '巽' },
  { deg: 180, glyph: '☲', name: '离' },
  { deg: 225, glyph: '☷', name: '坤' },
  { deg: 270, glyph: '☱', name: '兑' },
  { deg: 315, glyph: '☰', name: '乾' },
];

const DIR_CHARS = ['北', '东北', '东', '东南', '南', '西南', '西', '西北'];

function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

/** 三神标记的固定配色：喜=绛红 / 财=鎏金 / 福=青玉 */
const GOD_MARKS: { key: 'xi' | 'cai' | 'fu'; char: string; color: string }[] = [
  { key: 'xi', char: '喜', color: '#f4728f' },
  { key: 'cai', char: '财', color: '#d9b96a' },
  { key: 'fu', char: '福', color: '#5cbc8c' },
];

/**
 * 今日锦囊罗盘：静态方位字 + 缓慢旋转的八卦刻度环 + 中心太极。
 * 喜/财/福三神按当日方位点亮为彩色标记。
 */
export function AlmanacDial({
  xi,
  cai,
  fu,
  size = 150,
}: {
  xi?: string;
  cai?: string;
  fu?: string;
  size?: number;
}) {
  const C = 100; // 视窗中心
  const ticks = Array.from({ length: 60 }, (_, i) => i * 6);
  const marks = GOD_MARKS.map((g) => ({
    ...g,
    deg: dirToDeg(g.key === 'xi' ? xi : g.key === 'cai' ? cai : fu),
  })).filter((m) => m.deg != null);

  return (
    <svg
      viewBox="0 0 200 200"
      width={size}
      height={size}
      role="img"
      aria-label={`当日罗盘：喜神${xi ?? '—'}，财神${cai ?? '—'}，福神${fu ?? '—'}`}
      className="shrink-0"
    >
      {/* 底盘 */}
      <circle cx={C} cy={C} r="96" fill="none" stroke="var(--line)" strokeWidth="1" />
      <circle cx={C} cy={C} r="94" fill="none" stroke="var(--bd)" strokeWidth="0.6" />

      {/* 旋转环：刻度 + 八卦（脆、慢，painted-on-dial 的感觉） */}
      <g className="dial-spin" style={{ transformOrigin: '100px 100px' }}>
        {ticks.map((deg) => {
          const major = deg % 30 === 0;
          const [x1, y1] = polar(C, C, major ? 84 : 88, deg);
          const [x2, y2] = polar(C, C, 93, deg);
          return (
            <line
              key={deg}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="var(--t5)"
              strokeWidth={major ? 1.1 : 0.5}
              opacity={major ? 0.8 : 0.45}
            />
          );
        })}
        {TRIGRAMS.map((t) => {
          const [x, y] = polar(C, C, 70, t.deg);
          return (
            <text
              key={t.name}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="15"
              fill="var(--t3)"
              transform={`rotate(${t.deg} ${x} ${y})`}
            >
              {t.glyph}
            </text>
          );
        })}
      </g>

      {/* 静态方位字（罗盘参照系不动） */}
      {DIR_CHARS.map((ch, i) => {
        const [x, y] = polar(C, C, 84, i * 45);
        return (
          <text
            key={ch}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="8.5"
            fill="var(--t5)"
          >
            {ch}
          </text>
        );
      })}

      <circle cx={C} cy={C} r="48" fill="none" stroke="var(--line)" strokeWidth="0.7" />

      {/* 太极（缓慢反向自转，取「流转」之意） */}
      <g className="taiji-spin" style={{ transformOrigin: '100px 100px' }}>
        <circle cx={C} cy={C} r="19" fill="var(--card)" stroke="var(--t4)" strokeWidth="0.8" />
        <path
          d={`M ${C} ${C - 19} A 19 19 0 0 1 ${C} ${C + 19} A 9.5 9.5 0 0 1 ${C} ${C} A 9.5 9.5 0 0 0 ${C} ${C - 19} Z`}
          fill="var(--t1)"
          opacity="0.85"
        />
        <circle cx={C} cy={C - 9.5} r="2.6" fill="var(--t1)" opacity="0.85" />
        <circle cx={C} cy={C + 9.5} r="2.6" fill="var(--card)" />
      </g>

      {/* 三神方位标记 */}
      {marks.map((m) => {
        const [x, y] = polar(C, C, 34, m.deg!);
        return (
          <g key={m.key}>
            <circle cx={x} cy={y} r="10" fill={m.color} opacity="0.18" />
            <circle cx={x} cy={y} r="10" fill="none" stroke={m.color} strokeWidth="0.7" opacity="0.5" />
            <text
              x={x}
              y={y + 0.5}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize="10.5"
              fontWeight="700"
              fill={m.color}
            >
              {m.char}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** 中文色名 → hex（五行常用色 + 日常色），未知名称返回 null 由调用方回退 */
const COLOR_HEX: Record<string, string> = {
  白: '#f5f5f0',
  金: '#c9a227',
  银: '#c9ced6',
  黑: '#26262b',
  灰: '#8b9490',
  蓝: '#3b82f6',
  青: '#14b8a6',
  绿: '#22c55e',
  红: '#ef4444',
  朱: '#dc2626',
  紫: '#a855f7',
  黄: '#eab308',
  褐: '#92400e',
  棕: '#92400e',
  橙: '#f97316',
  粉: '#f472b6',
};

/** 把「白色/金色」这类幸运色文本渲染成真实色卡圆点 + 文字 */
export function ColorSwatches({ text, size = 14 }: { text: string; size?: number }) {
  const names = text
    .split(/[/、，,·\s]+/)
    .map((s) => s.replace(/色$/, '').trim())
    .filter(Boolean);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 align-middle">
      {names.map((n) => {
        const hex = COLOR_HEX[n];
        return (
          <span key={n} className="inline-flex items-center gap-1">
            {hex ? (
              <span
                className="inline-block rounded-full ring-1 ring-black/15"
                style={{ width: size, height: size, backgroundColor: hex }}
                title={`${n}色`}
              />
            ) : null}
            <span>{n}色</span>
          </span>
        );
      })}
    </span>
  );
}

/** 预测卡的域色主题：左侧渐变条 + 域字小印（未来页 renderRow 使用） */
export const DOMAIN_ACCENT: Record<string, { from: string; to: string; seal: string }> = {
  career: { from: '#818cf8', to: '#6366f1', seal: '业' },
  relationship: { from: '#fb9ab8', to: '#f43f5e', seal: '缘' },
  money: { from: '#e3c565', to: '#c9a227', seal: '财' },
  health: { from: '#6ee7b7', to: '#22c55e', seal: '康' },
  social: { from: '#fdba74', to: '#f97316', seal: '交' },
  study: { from: '#7dd3fc', to: '#0ea5e9', seal: '学' },
  travel: { from: '#5eead4', to: '#14b8a6', seal: '行' },
  purchase: { from: '#fcd34d', to: '#f59e0b', seal: '购' },
  habit: { from: '#c4b5fd', to: '#8b5cf6', seal: '习' },
};

/* ---------------- 五行（命盘页干支着色共用） ---------------- */

const GAN_WUXING: Record<string, string> = {
  甲: '木', 乙: '木', 丙: '火', 丁: '火', 戊: '土',
  己: '土', 庚: '金', 辛: '金', 壬: '水', 癸: '水',
};
const ZHI_WUXING: Record<string, string> = {
  子: '水', 丑: '土', 寅: '木', 卯: '木', 辰: '土', 巳: '火',
  午: '火', 未: '土', 申: '金', 酉: '金', 戌: '土', 亥: '水',
};

export function wuxingOfGan(g: string): string {
  return GAN_WUXING[g] ?? '';
}
export function wuxingOfZhi(z: string): string {
  return ZHI_WUXING[z] ?? '';
}

/** 五行主题色（金取鎏金而非纯白，保证两种主题下都可读） */
export const WUXING_COLOR: Record<string, string> = {
  木: '#2f9e6b',
  火: '#e04f3f',
  土: '#b07a2a',
  金: '#c9a227',
  水: '#3b82f6',
};

/** 紫微星曜亮度 → 展示层级（庙=鎏金重字，陷=极弱） */
export const BRIGHTNESS_CLS: Record<string, string> = {
  庙: 'text-gt font-semibold',
  旺: 'text-t1 font-semibold',
  得: 'text-t1',
  利: 'text-t2',
  平: 'text-t3',
  不: 'text-t4',
  陷: 'text-t5',
};

/** 四化标记配色：禄鎏金 / 权绛红 / 科天青 / 忌沉红 */
export const MUTAGEN_CLS: Record<string, string> = {
  禄: 'border-gilt-500/50 bg-gilt-500/15 text-gt',
  权: 'border-cinnabar-500/50 bg-cinnabar-500/15 text-cinnabar-400',
  科: 'border-sky-500/50 bg-sky-500/15 text-sky-400',
  忌: 'border-red-500/50 bg-red-500/10 text-red-500',
};

/** 迷你太极（命盘中宫等处的静饰） */
export function MiniTaiji({ size = 34, className = '' }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} className={className} aria-hidden>
      <circle cx="20" cy="20" r="19" fill="var(--card)" stroke="var(--t4)" strokeWidth="1" />
      <path
        d="M 20 1 A 19 19 0 0 1 20 39 A 9.5 9.5 0 0 1 20 20 A 9.5 9.5 0 0 0 20 1 Z"
        fill="var(--t1)"
        opacity="0.85"
      />
      <circle cx="20" cy="10.5" r="2.4" fill="var(--t1)" opacity="0.85" />
      <circle cx="20" cy="29.5" r="2.4" fill="var(--card)" />
    </svg>
  );
}

/** 星点明灭层：以 seed 确定性散布 ✦，卡片角落的氛围光尘（纯 CSS 动画，reduced-motion 下静止） */
export function Sparkles({
  count = 10,
  seed = 1,
  className = '',
}: {
  count?: number;
  seed?: number;
  className?: string;
}) {
  const stars = useMemo(() => {
    // mulberry32：同一 seed 永远同一布局，避免每次渲染星点跳位
    let s = seed >>> 0;
    const rnd = () => {
      s |= 0;
      s = (s + 0x6d2b79f5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    return Array.from({ length: count }, () => ({
      left: 3 + rnd() * 94,
      top: 4 + rnd() * 86,
      size: 7 + rnd() * 6,
      delay: rnd() * 3.4,
      dur: 2.2 + rnd() * 2.6,
    }));
  }, [count, seed]);
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      {stars.map((s, i) => (
        <span
          key={i}
          className="sparkle"
          style={{
            left: `${s.left}%`,
            top: `${s.top}%`,
            fontSize: s.size,
            animationDelay: `${s.delay}s`,
            ['--tw-dur' as string]: `${s.dur}s`,
          } as CSSProperties}
        >
          ✦
        </span>
      ))}
    </div>
  );
}
