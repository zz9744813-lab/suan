import { useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading } from '../components/ui';
import { SOURCE_LABEL, pct } from '../lib/format';
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

export default function Charts() {
  const engines = useAsync(() => api.engines(), []);
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const snapshot = useAsync(() => api.calendarSnapshot(DEFAULT_USER_ID, date), [date]);
  const [pid, setPid] = useState('');
  const detail = useAsync(
    () => (pid ? api.prediction(pid) : Promise.resolve(null)),
    [pid],
  );

  const payload = (snapshot.data?.payload ?? {}) as Record<string, any>;
  const bazi = payload.bazi ?? {};
  const shishen = payload.shishen ?? {};

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">命盘</h1>
        <p className="mt-1 text-xs text-slate-500">
          术式引擎状态、统一历法内核快照，以及每条预测的完整血缘。
        </p>
      </header>

      {/* 引擎状态 */}
      <Card
        title="术式引擎"
        subtitle="第 53 节：通过 Adapter 接入，输出统一 Signal。未接入的诚实降级，绝不假装可用"
      >
        {engines.loading && <Loading />}
        {engines.error && <ErrorBox message={engines.error} />}
        <div className="grid gap-2 md:grid-cols-2">
          {(engines.data?.engines ?? []).map((e) => (
            <div
              key={e.source}
              className="flex items-center justify-between rounded border border-ink-800 px-3 py-2"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-200">
                    {ENGINE_LABEL[e.source] ?? e.source}
                  </span>
                  <Badge tone={e.available ? 'good' : 'default'}>
                    {e.available ? '可用' : '未接入'}
                  </Badge>
                </div>
                <div className="mt-0.5 text-[11px] text-slate-600">
                  参考 {ENGINE_REF[e.source] ?? e.engine}
                </div>
              </div>
              <div className="text-right text-[11px] text-slate-700">{e.version}</div>
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
            className="rounded border border-ink-700 bg-ink-900 px-2 py-1 text-xs text-slate-200 focus:border-slate-600 focus:outline-none"
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
              <div className="mb-1 font-medium text-slate-400">目标日四柱</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {[
                  ['年', payload.year_ganzhi],
                  ['月', payload.month_ganzhi],
                  ['日', payload.day_ganzhi],
                  ['时', payload.hour_ganzhi],
                ].map(([k, v]) => (
                  <div key={k} className="rounded bg-ink-900 py-2">
                    <div className="text-[11px] text-slate-600">{k}</div>
                    <div className="mt-0.5 text-base text-slate-200">{v || '—'}</div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-slate-600">
                农历 {payload.lunar_year} 年 {payload.lunar_month} 月 {payload.lunar_day} 日
                {payload.is_leap_month ? '（闰月）' : ''}
              </div>
              <div className="text-slate-600">节气 {payload.current_jieqi || '—'}</div>
            </div>

            <div>
              <div className="mb-1 font-medium text-slate-400">本命八字</div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {[
                  ['年', bazi.year],
                  ['月', bazi.month],
                  ['日', bazi.day],
                  ['时', bazi.time],
                ].map(([k, v]) => (
                  <div key={k} className="rounded bg-ink-900 py-2">
                    <div className="text-[11px] text-slate-600">{k}</div>
                    <div className="mt-0.5 text-base text-slate-200">{v || '—'}</div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-slate-600">日主 {bazi.day_master || '—'}</div>
              <div className="text-slate-600">
                十神（天干） 年 {shishen.year || '—'} · 月 {shishen.month || '—'} · 时{' '}
                {shishen.time || '—'}
              </div>
              {payload.ming_gong && (
                <div className="text-slate-600">命宫 {payload.ming_gong}</div>
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
            className="flex-1 rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
          />
        </div>

        {pid && detail.loading && <Loading />}
        {pid && detail.error && <ErrorBox message={detail.error} />}
        {detail.data && (
          <div className="mt-3 space-y-3">
            <div className="flex items-center gap-2 text-sm text-slate-200">
              {detail.data.description}
              <Badge>{pct(detail.data.probability)}</Badge>
              {detail.data.integrity && (
                <Badge tone={detail.data.integrity.ok ? 'good' : 'bad'}>
                  {detail.data.integrity.ok ? '冻结完整' : '原文被篡改'}
                </Badge>
              )}
            </div>

            <div className="rounded border border-ink-800">
              <div className="border-b border-ink-800 px-3 py-1.5 text-xs text-slate-500">
                信号（第 14 节统一 Schema）
              </div>
              {detail.data.signals.length === 0 && (
                <div className="px-3 py-2 text-xs text-slate-600">无信号</div>
              )}
              <ul className="divide-y divide-ink-800">
                {detail.data.signals.map((s) => (
                  <li key={s.signal_id} className="px-3 py-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-300">
                        {SOURCE_LABEL[s.source] ?? s.source}
                      </span>
                      {s.degraded && <Badge tone="default">降级：{s.degrade_reason}</Badge>}
                      {s.dependency_group && (
                        <Badge tone="info">依赖组 {s.dependency_group}</Badge>
                      )}
                      <span className="ml-auto tabular text-slate-500">
                        direction {s.direction.toFixed(2)} · strength{' '}
                        {s.strength.toFixed(2)} · conf {s.confidence.toFixed(2)}
                      </span>
                    </div>
                    {s.evidence.length > 0 && (
                      <ul className="mt-1 space-y-0.5 text-slate-600">
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
              <div className="rounded bg-ink-900 p-2">
                <div className="mb-1 text-slate-500">证据依赖（第 20.12 节）</div>
                {Object.entries(detail.data.evidence_dependency).map(([g, srcs]) => (
                  <div key={g} className="text-slate-400">
                    {g}：{srcs.join('、')}
                    {srcs.length > 1 && (
                      <span className="ml-1 text-amber-400">
                        （{srcs.length} 源只算 1 份独立证据）
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="rounded bg-ink-900 p-2">
                <div className="mb-1 text-slate-500">版本（第 79 节）</div>
                {Object.entries(detail.data.versions).map(([k, v]) => (
                  <div key={k} className="text-slate-400">
                    {k}：{v}
                  </div>
                ))}
                <div className="mt-1 text-slate-600">
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
