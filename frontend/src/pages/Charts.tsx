import { useState } from 'react';

import { api, DEFAULT_USER_ID, type FortuneReading } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, PrimaryButton, inputCls } from '../components/ui';
import { SOURCE_LABEL, cleanDescription, pct } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 6 节 Metaphysical Engine
 * 第 49 节 Prediction Detail（完全可解释）
 * 第 80 节 Prediction Lineage
 */

const ENGINE_LABEL: Record<string, string> = {
  ziwei: '紫微斗数',
  bazi: '八字',
  qimen: '奇门遁甲',
  liuyao: '六爻',
  meihua: '梅花易数',
  palm: '掌纹',
  face: '面相',
};

const ENGINE_REF: Record<string, string> = {
  ziwei: 'SylarLong/iztro',
  bazi: '6tail/lunar-python',
  qimen: 'Maximilian-Winter/Qimen-Dunjia',
  liuyao: 'Johnson-Jia/liuyao-divination',
  meihua: 'handsomejustin/meihua-yi',
  palm: 'yeonsumia/palmistry + MediaPipe',
  face: 'MediaPipe Face Landmark',
};

/** 批示维度 → 图标 + 说明 */
const READING_META: { key: string; label: string; icon: string }[] = [
  { key: '命格总论', label: '命格总论', icon: '命' },
  { key: '事业', label: '事业', icon: '业' },
  { key: '财运', label: '财运', icon: '财' },
  { key: '婚恋', label: '婚恋', icon: '姻' },
  { key: '健康', label: '健康', icon: '健' },
  { key: '未来5年', label: '未来 5 年', icon: '5' },
  { key: '未来10年', label: '未来 10 年', icon: '10' },
];

/** 命理批示区块（大运时间轴 + 流年 + 批示卡片） */
function FortuneSection({ data }: { data: FortuneReading }) {
  const chart = data.chart;
  if (!chart) {
    return <ErrorBox message={data.error ?? '命盘排盘失败'} />;
  }

  const bazi = chart.bazi ?? {};
  const pillars = [
    ['年柱', bazi.year],
    ['月柱', bazi.month],
    ['日柱', bazi.day],
    ['时柱', bazi.time],
  ];

  const dayun = chart.dayun ?? [];
  // 当前精确周岁（后端已算好，前端直接用）；为 null 时回退到年份差近似
  const currentAgeExact = chart.current_age_exact;
  const nowYear = new Date().getFullYear();
  const fallbackAge = nowYear - (chart.liunian?.[0]?.age ?? 0);

  return (
    <div className="space-y-5">
      {/* 四柱 + 五行 + 十神 */}
      <Card
        title="本命八字"
        subtitle={`日主 ${chart.day_master} · 命宫 ${chart.ming_gong || '—'} · ${
          chart.birth_time_known ? '时辰已确认' : '时辰未知（时柱存疑）'
        }`}
      >
        <div className="grid grid-cols-4 gap-2 text-center">
          {pillars.map(([k, v]) => (
            <div key={k} className="rounded-xl border border-line bg-panel py-3">
              <div className="text-[11px] text-t4">{k}</div>
              <div className="mt-1 font-serif text-xl font-semibold tracking-[0.15em] text-gt">
                {v || '—'}
              </div>
              <div className="mt-1 text-[11px] text-t3">
                五行 {chart.wuxing?.[k === '年柱' ? 'year' : k === '月柱' ? 'month' : k === '日柱' ? 'day' : 'time'] ?? '—'}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
          {(['year', 'month', 'day', 'time'] as const).map((k) => (
            <div key={k} className="rounded-lg bg-panel px-3 py-2">
              <div className="text-t4">
                {k === 'year' ? '年' : k === 'month' ? '月' : k === 'day' ? '日' : '时'} 十神
              </div>
              <div className="mt-0.5 text-t1">{chart.shishen?.[k] ?? '—'}</div>
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-t4">
          <span>纳音：{['year', 'month', 'day', 'time'].map((k) => chart.nayin?.[k]).filter(Boolean).join(' · ') || '—'}</span>
        </div>
      </Card>

      {/* 大运时间轴 */}
      <Card title="大运" subtitle="每十年一换的大运干支，标出当前所处大运">
        {dayun.length === 0 ? (
          <EmptyState>暂无大运数据</EmptyState>
        ) : (
          <div className="flex items-stretch gap-0 overflow-x-auto pb-1">
            {dayun.map((d, i) => {
              // 当前大运：根据"是否本年生日已过"反推实际周岁，再对照 start_age
              const effectiveAge = currentAgeExact != null ? currentAgeExact : fallbackAge;
              const isCurrent =
                effectiveAge != null && effectiveAge >= d.start_age && i < dayun.length - 1 && effectiveAge < dayun[i + 1].start_age;
              return (
                <div key={i} className="flex min-w-[76px] flex-1 items-center">
                  <div
                    className={`flex w-full flex-col items-center gap-1 rounded-lg border px-1 py-2 text-center transition-colors ${
                      isCurrent
                        ? 'border-gilt-500/60 bg-gilt-500/15'
                        : 'border-line bg-panel'
                    }`}
                  >
                    <span className={`font-serif text-base font-semibold tracking-wide ${isCurrent ? 'text-gt' : 'text-t1'}`}>
                      {d.ganzhi}
                    </span>
                    <span className="text-[10px] text-t4">{d.start_age} 岁</span>
                    <span className="text-[10px] text-t5">{d.start_year}</span>
                    {isCurrent && (
                      <Badge tone="gilt">当前</Badge>
                    )}
                  </div>
                  {i < dayun.length - 1 && (
                    <div className={`h-px w-2 shrink-0 ${isCurrent ? 'bg-gilt-500/50' : 'bg-panel'}`} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* 流年运势表 */}
      <Card title="流年运势" subtitle="未来十年的流年干支与生肖">
        {!chart.liunian || chart.liunian.length === 0 ? (
          <EmptyState>暂无流年数据</EmptyState>
        ) : (
          <div className="grid grid-cols-5 gap-2 text-center md:grid-cols-10">
            {chart.liunian.map((ly) => (
              <div key={ly.year} className="rounded-lg border border-line bg-panel py-2.5">
                <div className="text-[11px] text-t4">{ly.year}</div>
                <div className="mt-0.5 font-serif text-lg font-semibold tracking-wider text-gt">
                  {ly.ganzhi}
                </div>
                <div className="text-[10px] text-t4">
                  {ly.zodiac}年{ly.age != null ? ` · ${ly.age}岁` : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* LLM 批示卡片 */}
      <Card
        title="命理批示"
        subtitle="传统术数参考解读，非科学预测；不诊断疾病、不替代医疗/法律/财务建议"
      >
        {!data.reading ? (
          <ErrorBox message={data.error ?? '批示生成失败（可重试）'} />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {READING_META.map((m) => {
              const text = data.reading?.[m.key];
              if (!text) return null;
              const isWide = m.key === '命格总论' || m.key === '未来10年';
              return (
                <div
                  key={m.key}
                  className={`rounded-xl border border-bd bg-panel p-4 ${isWide ? 'md:col-span-2' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-md border border-gilt-500/30 bg-gilt-500/10 text-xs font-semibold text-gt">
                      {m.icon}
                    </span>
                    <span className="text-sm font-medium text-t1">{m.label}</span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-t2">{text}</p>
                </div>
              );
            })}
          </div>
        )}
        <div className="mt-3 flex items-center gap-2 text-[11px] text-t4">
          模型 {data.model || '—'} · {((data.duration_ms ?? 0) / 1000).toFixed(1)}s
          {data.cached && (
            <span className="rounded border border-bd bg-panel px-1.5 py-0.5 text-t3">
              命中缓存（秒开）
            </span>
          )}
        </div>
        {/* 推理链路（思考过程）可折叠展示——命理批示的推理依据，增强可解释性 */}
        {data.reasoning && (
          <details className="mt-3 rounded-xl border border-bd bg-panel p-3">
            <summary className="cursor-pointer text-xs font-medium text-t3 hover:text-t1">
              查看模型推理链路（思考过程）
            </summary>
            <pre className="mt-2 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-t4">
              {data.reasoning}
            </pre>
          </details>
        )}
      </Card>
    </div>
  );
}

export default function Charts() {
  const engines = useAsync(() => api.engines(), []);
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const snapshot = useAsync(() => api.calendarSnapshot(DEFAULT_USER_ID, date), [date]);
  const [pid, setPid] = useState('');
  const detail = useAsync(
    () => (pid ? api.prediction(pid) : Promise.resolve(null)),
    [pid],
  );

  // 命理批示（默认走缓存，命中则秒出；「重新生成」才强制重算）
  const [refreshNonce, setRefreshNonce] = useState(0);
  const fortune = useAsync(
    () => api.fortuneReading(DEFAULT_USER_ID, refreshNonce > 0),
    [refreshNonce],
  );

  const payload = (snapshot.data?.payload ?? {}) as Record<string, any>;

  return (
    <div className="space-y-5">
      <PageHeader
        title="命盘"
        desc="本命八字、大运流年与命理批示。传统术数参考，非科学预测。"
        right={
          <PrimaryButton onClick={() => setRefreshNonce((n) => n + 1)} busy={fortune.loading}>
            {fortune.loading ? '批示生成中，约 2-3 分钟…' : '重新生成批示'}
          </PrimaryButton>
        }
      />

      {/* 命理批示（核心展示） */}
      {fortune.loading && <Loading label="正在排盘并生成命理批示（推理模型思考 + 正文，约 2-3 分钟，请耐心等待）…" />}
      {fortune.error && <ErrorBox message={fortune.error} />}
      {!fortune.loading && !fortune.error && fortune.data && (
        <FortuneSection data={fortune.data} />
      )}

      {/* 术式引擎 */}
      <Card
        title="术式引擎"
        subtitle="第 53 节：通过 Adapter 接入，输出统一 Signal。未接入的诚实降级，绝不假装可用"
      >
        {engines.loading && <Loading />}
        {engines.error && <ErrorBox message={engines.error} />}
        <div className="stagger grid gap-2 md:grid-cols-2">
          {(engines.data?.engines ?? []).map((e) => (
            <div
              key={e.source}
              className="row-hover flex items-center justify-between rounded-lg border border-line px-3 py-2"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-t1">
                    {ENGINE_LABEL[e.source] ?? e.source}
                  </span>
                  <Badge tone={e.available ? 'good' : 'default'}>
                    {e.available ? '可用' : '未接入'}
                  </Badge>
                </div>
                <div className="mt-0.5 text-[11px] text-t4">
                  参考 {ENGINE_REF[e.source] ?? e.engine}
                </div>
              </div>
              <div className="text-right text-[11px] text-t5">{e.version}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 历法快照 */}
      <Card
        title="历法内核快照"
        subtitle="第 6 节：所有术式共享同一个 Calendar Core，禁止各模块自己算日期"
        right={
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputCls}
          />
        }
      >
        {snapshot.loading && <Loading />}
        {snapshot.error && <ErrorBox message={snapshot.error} />}
        {!snapshot.loading && !snapshot.error && snapshot.data?.degraded && (
          <ErrorBox message={`引擎降级：${String(snapshot.data.degrade_reason)}`} />
        )}
        {!snapshot.loading && !snapshot.error && !snapshot.data?.degraded && (
          <div className="grid gap-4 text-xs md:grid-cols-2">
            <div>
              <div className="mb-1 font-medium text-t2">目标日四柱</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {[
                  ['年', payload.year_ganzhi],
                  ['月', payload.month_ganzhi],
                  ['日', payload.day_ganzhi],
                  ['时', payload.hour_ganzhi],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-line bg-panel py-2.5">
                    <div className="text-[11px] text-t4">{k}</div>
                    <div className="mt-1 font-serif text-lg font-semibold tracking-[0.15em] text-gt">
                      {v || '—'}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-t4">
                农历 {payload.lunar_year} 年 {payload.lunar_month} 月 {payload.lunar_day} 日
                {payload.is_leap_month ? '（闰月）' : ''}
              </div>
              <div className="text-t4">节气 {payload.current_jieqi || '—'}</div>
            </div>

            <div>
              <div className="mb-1 font-medium text-t2">本命八字</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {[
                  ['年', payload.bazi?.year],
                  ['月', payload.bazi?.month],
                  ['日', payload.bazi?.day],
                  ['时', payload.bazi?.time],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-line bg-panel py-2.5">
                    <div className="text-[11px] text-t4">{k}</div>
                    <div className="mt-1 font-serif text-lg font-semibold tracking-[0.15em] text-gt">
                      {v || '—'}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-t4">日主 {payload.bazi?.day_master || '—'}</div>
              <div className="text-t4">
                十神（天干） 年 {payload.shishen?.year || '—'} · 月 {payload.shishen?.month || '—'} · 时{' '}
                {payload.shishen?.time || '—'}
              </div>
              {payload.ming_gong && (
                <div className="text-t4">命宫 {payload.ming_gong}</div>
              )}
            </div>
          </div>
        )}
      </Card>

      {/* 预测血缘 */}
      <Card
        title="预测血缘"
        subtitle="第 80 节：任意一条预测都能追溯到候选 / 信号 / 规则 / Agent / Prompt / 模型"
      >
        <div className="flex gap-2">
          <input
            value={pid}
            onChange={(e) => setPid(e.target.value)}
            placeholder="输入 prediction_id"
            className={`flex-1 ${inputCls}`}
          />
        </div>

        {pid && detail.loading && <Loading />}
        {pid && detail.error && <ErrorBox message={detail.error} />}
        {detail.data && (
          <div className="mt-3 space-y-3">
            <div className="flex items-center gap-2 text-sm text-t1">
              {cleanDescription(detail.data.description, detail.data.event_type)}
              <Badge>{pct(detail.data.probability)}</Badge>
              {detail.data.integrity && (
                <Badge tone={detail.data.integrity.ok ? 'good' : 'bad'}>
                  {detail.data.integrity.ok ? '冻结完整' : '原文被篡改'}
                </Badge>
              )}
            </div>

            <div className="rounded border border-line">
              <div className="border-b border-line px-3 py-1.5 text-xs text-t3">
                信号（第 14 节统一 Schema）
              </div>
              {detail.data.signals.length === 0 && (
                <div className="px-3 py-2 text-xs text-t4">无信号</div>
              )}
              <ul className="divide-y divide-line">
                {detail.data.signals.map((s) => (
                  <li key={s.signal_id} className="px-3 py-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-t1">
                        {SOURCE_LABEL[s.source] ?? s.source}
                      </span>
                      {s.degraded && <Badge tone="default">降级：{s.degrade_reason}</Badge>}
                      {s.dependency_group && (
                        <Badge tone="info">依赖组 {s.dependency_group}</Badge>
                      )}
                      <span className="ml-auto tabular text-t3">
                        direction {s.direction.toFixed(2)} · strength{' '}
                        {s.strength.toFixed(2)} · conf {s.confidence.toFixed(2)}
                      </span>
                    </div>
                    {s.evidence.length > 0 && (
                      <ul className="mt-1 space-y-0.5 text-t4">
                        {s.evidence.map((e, i) => (
                          <li key={i}>
                            · [{e.source}] {e.description}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className="grid gap-2 text-xs md:grid-cols-2">
              <div className="rounded bg-panel p-2">
                <div className="mb-1 text-t3">证据依赖（第 20.12 节）</div>
                {Object.entries(detail.data.evidence_dependency).map(([g, srcs]) => (
                  <div key={g} className="text-t2">
                    {g}：{srcs.join('、')}
                    {srcs.length > 1 && (
                      <span className="ml-1 text-amber-400">
                        （{srcs.length} 源只算 1 份独立证据）
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="rounded bg-panel p-2">
                <div className="mb-1 text-t3">版本（第 79 节）</div>
                {Object.entries(detail.data.versions).map(([k, v]) => (
                  <div key={k} className="text-t2">
                    {k}：{v}
                  </div>
                ))}
                <div className="mt-1 text-t4">
                  Agent 分歧 {detail.data.agent_disagreement.toFixed(3)}
                </div>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
