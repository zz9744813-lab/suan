/**
 * 推演仪式动画 —— 每个术式在等待结果时展现符合其传统仪程的动效。
 *
 * 全部为自绘 SVG / CSS 动效，无外链素材；所有动画类都在 index.css 的
 * prefers-reduced-motion 块中降级（静态呈现）。
 *
 * 诚实地说明：后端 7 个 adapter 是并行盲采的一次同步调用，这里播放的是
 * 推演「过程演出」，逐个轮转 —— 它不承担也不假装承担进度上报。
 */

import { useEffect, useState } from 'react';

import { MiniTaiji, Sparkles, WUXING_COLOR, wuxingOfGan, wuxingOfZhi } from './almanac';

export type EngineKey =
  | 'bazi'
  | 'ziwei'
  | 'liuyao'
  | 'meihua'
  | 'qimen'
  | 'palm'
  | 'face';

/** 轮转顺序：术数在前，相学殿后 */
export const RITUAL_ORDER: EngineKey[] = [
  'bazi',
  'ziwei',
  'liuyao',
  'meihua',
  'qimen',
  'palm',
  'face',
];

export const ENGINE_RITUAL: Record<EngineKey, { name: string; act: string }> = {
  bazi: { name: '八字', act: '排四柱' },
  ziwei: { name: '紫微', act: '布十二宫' },
  liuyao: { name: '六爻', act: '摇钱成卦' },
  meihua: { name: '梅花', act: '取数起卦' },
  qimen: { name: '奇门', act: '转九宫天盘' },
  palm: { name: '掌纹', act: '描三道纹' },
  face: { name: '面相', act: '三停扫描' },
};

const GANS = '甲乙丙丁戊己庚辛壬癸'.split('');
const ZHIS = '子丑寅卯辰巳午未申酉戌亥'.split('');

/* ------------------------------------------------------------------ */
/* 六爻：三枚铜钱不断翻转 + 六条爻线自下而上落定                        */
/* ------------------------------------------------------------------ */
function LiuyaoRitual() {
  return (
    <svg viewBox="0 0 96 96" width="100%" height="100%" aria-hidden>
      {[0, 1, 2].map((i) => (
        <g key={i} className="ritual-coin" style={{ animationDelay: `${i * 0.24}s` }}>
          <circle cx={26 + i * 22} cy={30} r={11} fill="none" stroke="currentColor" strokeWidth={2} />
          <rect
            x={26 + i * 22 - 3.5}
            y={30 - 3.5}
            width={7}
            height={7}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
          />
        </g>
      ))}
      {/* 爻线：初爻在下落定，间隔位画断爻（阴）示意阴阳相生 */}
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const y = 84 - i * 8;
        const delay = `${i * 0.52}s`;
        return i % 2 === 0 ? (
          <rect key={i} className="ritual-yao" style={{ animationDelay: delay }} x={30} y={y} width={36} height={3.6} rx={1.8} fill="currentColor" />
        ) : (
          <g key={i} className="ritual-yao" style={{ animationDelay: delay }}>
            <rect x={30} y={y} width={15} height={3.6} rx={1.8} fill="currentColor" />
            <rect x={51} y={y} width={15} height={3.6} rx={1.8} fill="currentColor" />
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* 梅花易数：两轴数字卷帘 + 上下卦象交替显影                            */
/* ------------------------------------------------------------------ */
const REEL_DIGITS = '一二三四五六七八九'.split('');
function MeihuaRitual() {
  return (
    <div className="flex h-full w-full items-center justify-center gap-3">
      {[0, 1].map((col) => (
        <div key={col} className="h-11 w-7 overflow-hidden rounded-md border border-line bg-panel">
          <div className="ritual-reel" style={{ animationDelay: `${col * 0.4}s` }}>
            {[...REEL_DIGITS, ...REEL_DIGITS].map((d, i) => (
              <div key={i} className="flex h-11 w-full items-center justify-center text-base text-t1">
                {d}
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="flex flex-col items-center leading-none">
        <span className="ritual-flicker block text-xl text-gt">☴</span>
        <span className="ritual-flicker block text-xl text-gt" style={{ animationDelay: '0.9s' }}>
          ☳
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 奇门遁甲：外圈八门缓转的九宫天盘                                     */
/* ------------------------------------------------------------------ */
const QIMEN_DOORS = '休生伤杜景死惊开'.split('');
function QimenRitual() {
  return (
    <svg viewBox="0 0 96 96" width="100%" height="100%" aria-hidden>
      <g className="qimen-ring">
        {QIMEN_DOORS.map((door, i) => {
          const ang = (i * 45 - 90) * (Math.PI / 180);
          return (
            <text
              key={door}
              x={48 + Math.cos(ang) * 41}
              y={48 + Math.sin(ang) * 41}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={8.5}
              fill="currentColor"
              opacity={0.72}
            >
              {door}
            </text>
          );
        })}
      </g>
      {[0, 1, 2].map((r) =>
        [0, 1, 2].map((c) => {
          const idx = r * 3 + c;
          return (
            <rect
              key={idx}
              className="ritual-qcell"
              style={{ animationDelay: `${-idx * 0.3}s` }}
              x={24 + c * 17}
              y={24 + r * 17}
              width={15}
              height={15}
              rx={2}
              fill="var(--glow-gold, rgba(201,162,39,0.5))"
              stroke="currentColor"
              strokeWidth={0.8}
            />
          );
        }),
      )}
      <text x={48} y={49} textAnchor="middle" dominantBaseline="central" fontSize={8} fill="currentColor" fontWeight={600}>
        符
      </text>
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* 八字：四柱干支走马换字（立柱落定式翻牌）                             */
/* ------------------------------------------------------------------ */
const PILLAR_LABELS = ['年', '月', '日', '时'];
function BaziRitual() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((v) => v + 1), 160);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="flex h-full w-full items-center justify-center gap-[3px]" style={{ perspective: 320 }}>
      {PILLAR_LABELS.map((name, i) => {
        const gan = GANS[(t + i * 3) % 10];
        const zhi = ZHIS[(t + i * 5) % 12];
        return (
          <div key={name} className="flex flex-col items-center gap-0.5">
            <span className="text-[8px] leading-none text-t5">{name}</span>
            {[gan, zhi].map((ch, row) => (
              <div
                key={`${row}-${t}`}
                className="ritual-charflip flex h-[26px] w-[16px] items-center justify-center rounded border border-line bg-panel text-[13px] font-semibold"
                style={{
                  color:
                    WUXING_COLOR[row === 0 ? wuxingOfGan(ch) : wuxingOfZhi(ch)] ??
                    'var(--t1)',
                }}
              >
                {ch}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 紫微：十二宫小盘逐宫点亮 + 中宫太极缓转                              */
/* ------------------------------------------------------------------ */
const ZW_RING: [number, number][] = [
  [1, 1], [1, 2], [1, 3], [1, 4],
  [2, 4], [3, 4],
  [4, 4], [4, 3], [4, 2], [4, 1],
  [3, 1], [2, 1],
];
function ZiweiRitual() {
  return (
    <div className="grid h-full w-full grid-cols-4 grid-rows-4 gap-[3px] p-1">
      {ZW_RING.map(([r, c], i) => (
        <div
          key={i}
          className="ritual-zcell rounded-[4px] border border-line bg-panel"
          style={{ gridRowStart: r, gridColumnStart: c, animationDelay: `${-i * 0.4}s` }}
        />
      ))}
      <div
        className="flex items-center justify-center"
        style={{ gridRowStart: 2, gridColumnStart: 2, gridRowEnd: 4, gridColumnEnd: 4 }}
      >
        <span className="block" style={{ animation: 'spin360 16s linear infinite' }}>
          <MiniTaiji size={34} />
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 掌纹：掌心三道纹逐笔描出                                             */
/* ------------------------------------------------------------------ */
function PalmRitual() {
  return (
    <svg viewBox="0 0 96 96" width="100%" height="100%" fill="none" aria-hidden>
      {/* 掌形轮廓（静底） */}
      <path
        d="M30 88 Q18 78 19 58 L20 40 Q21 20 35 16 Q49 12 61 18 Q75 25 75 44 L75 60 Q75 78 62 88"
        stroke="currentColor"
        strokeOpacity={0.3}
        strokeWidth={1.6}
      />
      <path d="M20 52 Q8 50 10 40 Q12 31 21 33" stroke="currentColor" strokeOpacity={0.3} strokeWidth={1.6} />
      {/* 感情线 / 智慧线 / 生命线 */}
      <path className="ritual-draw" d="M26 34 Q48 25 70 33" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
      <path className="ritual-draw" style={{ animationDelay: '0.65s' }} d="M26 47 Q48 43 68 53" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
      <path className="ritual-draw" style={{ animationDelay: '1.3s' }} d="M32 22 Q22 46 34 74" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* 面相：三停刻度 + 扫描线上下往复 + 五官点位随扫点亮                   */
/* ------------------------------------------------------------------ */
function FaceRitual() {
  return (
    <svg viewBox="0 0 96 96" width="100%" height="100%" fill="none" aria-hidden>
      <ellipse cx={48} cy={48} rx={26} ry={34} stroke="currentColor" strokeOpacity={0.4} strokeWidth={1.6} />
      {[34, 50, 66].map((y) => (
        <line key={y} x1={24} x2={72} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.25} strokeDasharray="3 3" strokeWidth={1} />
      ))}
      {/* 扫描线 */}
      <rect className="ritual-scanline" x={24} y={47.5} width={48} height={2.4} rx={1.2} fill="rgba(201,162,39,0.55)" />
      {/* 目 / 鼻 / 口 点位 */}
      {[[38, 42], [58, 42], [48, 55], [48, 66]].map(([x, y], i) => (
        <circle key={i} className="ritual-flicker" style={{ animationDelay: `${i * 0.55}s` }} cx={x} cy={y} r={2.2} fill="currentColor" />
      ))}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* 单术式仪式（含名称签注）                                             */
/* ------------------------------------------------------------------ */
export function EngineRitual({
  engine,
  size = 96,
  withCaption = true,
}: {
  engine: EngineKey;
  size?: number;
  withCaption?: boolean;
}) {
  const meta = ENGINE_RITUAL[engine];
  const visual =
    engine === 'liuyao' ? (
      <LiuyaoRitual />
    ) : engine === 'meihua' ? (
      <MeihuaRitual />
    ) : engine === 'qimen' ? (
      <QimenRitual />
    ) : engine === 'bazi' ? (
      <BaziRitual />
    ) : engine === 'ziwei' ? (
      <ZiweiRitual />
    ) : engine === 'palm' ? (
      <PalmRitual />
    ) : (
      <FaceRitual />
    );
  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="rounded-xl border border-line bg-panel/60 p-2 text-t2"
        style={{ width: size, height: size }}
      >
        {visual}
      </div>
      {withCaption && (
        <div className="text-xs text-t3">
          <span className="font-medium text-t1">{meta.name}</span>
          <span className="mx-1 text-t5">·</span>
          {meta.act}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 推演舞台：生成期间轮转七术式仪式                                     */
/* ------------------------------------------------------------------ */
export function DivinationStage({ active, done }: { active: boolean; done: boolean }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!active) return;
    setStep(0);
    const id = setInterval(() => setStep((s) => (s + 1) % RITUAL_ORDER.length), 1600);
    return () => clearInterval(id);
  }, [active]);

  const current = active ? step : -1;
  const finished = !active && done;

  return (
    <div className="mt-4 flex flex-col items-start gap-4 border-t border-bd/60 pt-4 sm:flex-row sm:items-center">
      {/* 左侧：当前术式的仪式动画 */}
      <div className="flex shrink-0 items-center justify-center">
        {finished ? (
          <div className="flex flex-col items-center gap-2">
            <div className="taiji-halo relative flex h-24 w-24 items-center justify-center rounded-xl border border-gilt-500/40 bg-gilt-500/[0.07] text-gt">
              <Sparkles count={4} seed={3} />
              <span className="block" style={{ animation: 'spin360 18s linear infinite' }}>
                <MiniTaiji size={52} />
              </span>
            </div>
            <div className="text-xs font-medium text-gt">七术式信号已收录</div>
          </div>
        ) : (
          <EngineRitual engine={RITUAL_ORDER[Math.max(current, 0)]} size={96} />
        )}
      </div>
      {/* 右侧：七术式状态条 */}
      <div className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1.5 md:grid-cols-4">
        {RITUAL_ORDER.map((key, i) => {
          const meta = ENGINE_RITUAL[key];
          const state = finished ? 'done' : i === current ? 'doing' : 'wait';
          return (
            <div key={key} className="flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-500 ${
                  state === 'done'
                    ? 'bg-jade-500'
                    : state === 'doing'
                      ? 'status-dot bg-gilt-400'
                      : 'bg-line'
                }`}
              />
              <span
                className={`text-xs transition-colors duration-500 ${
                  state === 'doing' ? 'font-medium text-t1' : state === 'done' ? 'text-t3' : 'text-t5'
                }`}
              >
                {meta.name}
              </span>
              <span className="text-[10px] text-t5">
                {state === 'done' ? '已收录' : state === 'doing' ? meta.act + '…' : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 批示等待态：仪式动画 + 提示语（Charts 页用）                         */
/* ------------------------------------------------------------------ */
export function RitualLoading({ engine, label }: { engine: EngineKey; label: string }) {
  return (
    <div className="animate-fade-in flex flex-col items-center gap-3 py-6" role="status" aria-label={label}>
      <EngineRitual engine={engine} size={104} />
      <div className="text-xs text-t4">{label}</div>
    </div>
  );
}
