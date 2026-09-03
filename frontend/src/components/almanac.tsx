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
