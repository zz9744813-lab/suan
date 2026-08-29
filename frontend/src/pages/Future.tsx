import { useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading, ProbBar, Stat } from '../components/ui';
import {
  DOMAIN_LABEL,
  SCALE_LABEL,
  STATUS_LABEL,
  pct,
  shortDate,
  shortDateTime,
} from '../lib/format';
import { useAsync } from '../lib/useAsync';

const SCALES = [
  { key: 'day', label: 'TODAY' },
  { key: 'week', label: '7 DAYS' },
  { key: 'month', label: '30 DAYS' },
  { key: 'year', label: '90 DAYS' },
] as const;

export default function Future() {
  const [scale, setScale] = useState<string>('day');
  const [generating, setGenerating] = useState(false);
  const [notes, setNotes] = useState<string[] | null>(null);

  const preds = useAsync(() => api.listPredictions(DEFAULT_USER_ID), []);
  const overall = useAsync(() => api.overall(DEFAULT_USER_ID), []);
  const due = useAsync(() => api.duePredictions(DEFAULT_USER_ID), []);
  const health = useAsync(() => api.health(), []);
  const tree = useAsync(() => api.futureTree(DEFAULT_USER_ID), []);

  const visible = (preds.data?.items ?? []).filter(
    (p) => p.time_scale === scale || scale === 'day',
  );

  const generate = async () => {
    setGenerating(true);
    setNotes(null);
    try {
      const r = await api.generate(DEFAULT_USER_ID, scale, 20);
      setNotes([
        ...r.notes,
        ...r.rejected.map((x) => `拦截 ${x.event_type}（${x.decision}）：${x.reasons[0] ?? ''}`),
      ]);
      preds.reload();
      overall.reload();
      due.reload();
    } catch (e) {
      setNotes([e instanceof Error ? e.message : String(e)]);
    } finally {
      setGenerating(false);
    }
  };

  const engineOk = health.data
    ? Object.values(health.data.engines).filter((e) => e.available).length
    : 0;
  const engineTotal = health.data ? Object.keys(health.data.engines).length : 7;

  return (
    <div className="space-y-5">
      {/* 头部：方案第 48 节 Future Dashboard */}
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">未来</h1>
          <p className="mt-1 text-xs text-slate-500">
            系统主动生成预测并冻结，等待现实检验。候选不等于正式预测。
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={engineOk > 0 ? 'good' : 'warn'}>
            引擎 {engineOk}/{engineTotal} 可用
          </Badge>
          <button
            onClick={generate}
            disabled={generating}
            className="rounded bg-slate-200 px-3 py-1.5 text-sm font-medium text-ink-950 transition hover:bg-white disabled:opacity-50"
          >
            {generating ? '生成中…' : '生成预测'}
          </button>
        </div>
      </header>

      {notes && (
        <Card title="本轮运行记录" subtitle="含被对抗性 Gate 拦截的候选">
          <ul className="space-y-1 text-xs text-slate-400">
            {notes.map((n, i) => (
              <li key={i}>· {n}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* 尺度切换 */}
      <div className="flex gap-1 border-b border-ink-800">
        {SCALES.map((s) => (
          <button
            key={s.key}
            onClick={() => setScale(s.key)}
            className={`px-3 py-2 text-xs font-medium tracking-wide transition ${
              scale === s.key
                ? 'border-b-2 border-slate-200 text-slate-100'
                : 'text-slate-600 hover:text-slate-400'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 概览指标 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="待验证" value={due.data?.count ?? '—'} hint="到期需用户确认" />
        <Stat
          label="已验证"
          value={overall.data?.sample_size ?? '—'}
          hint="进入评分的样本"
        />
        <Stat
          label="Skill Score"
          value={
            overall.data?.skill_score != null ? pct(overall.data.skill_score, 1) : '—'
          }
          hint="相对 Null Model"
          tone={(overall.data?.skill_score ?? 0) > 0 ? 'good' : 'bad'}
        />
        <Stat
          label="Brier"
          value={overall.data ? overall.data.brier.toFixed(3) : '—'}
          hint="越低越好"
          tone={(overall.data?.brier ?? 1) < 0.25 ? 'good' : 'warn'}
        />
      </div>

      {/* 预测列表 */}
      <Card
        title="正式冻结预测"
        subtitle="只有通过对抗性 Gate 并获得预算额度的预测才会出现在这里"
      >
        {preds.loading && <Loading />}
        {preds.error && <ErrorBox message={preds.error} />}
        {!preds.loading && !preds.error && visible.length === 0 && (
          <EmptyState>
            暂无预测。点击右上角「生成预测」跑一次闭环：
            <br />
            扫描候选 → 盲审 → 融合 → 对抗审查 → 预算竞争 → 冻结。
          </EmptyState>
        )}
        <ul className="space-y-3">
          {visible.map((p) => (
            <li key={p.prediction_id} className="rounded border border-ink-800 p-3">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-200">{p.description}</span>
                    <Badge>{DOMAIN_LABEL[p.domain] ?? p.domain}</Badge>
                    <Badge tone="info">{SCALE_LABEL[p.time_scale]}</Badge>
                    {p.visibility_mode === 'HIDDEN' && (
                      <Badge tone="warn">隐藏模式</Badge>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {p.event_type} · 窗口 {shortDate(p.window[0])} ~ {shortDate(p.window[1])}
                    {p.verification_due_at && ` · 验证截止 ${shortDateTime(p.verification_due_at)}`}
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <ProbBar p={p.probability} className="w-40" />
                    <span className="text-sm font-semibold tabular text-slate-200">
                      {pct(p.probability)}
                    </span>
                    {p.null_probability != null && (
                      <span className="text-xs text-slate-600">
                        Null 基线 {pct(p.null_probability)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <Badge
                    tone={
                      p.status === 'VERIFIED'
                        ? 'good'
                        : p.status === 'REJECTED' || p.status === 'LEAKED'
                          ? 'bad'
                          : 'default'
                    }
                  >
                    {STATUS_LABEL[p.status] ?? p.status}
                  </Badge>
                  <div className="mt-1 font-mono text-[10px] text-slate-700">
                    {p.sha256_head}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {/* 第 27 节 Future Tree：人生情景树（每周按新证据重算） */}
      <Card
        title="人生情景树"
        subtitle="第 27 节：Future Tree 每周按新证据重算 P(Scenario | New Evidence)"
      >
        {tree.loading && <Loading />}
        {tree.error && <ErrorBox message={tree.error} />}
        {!tree.loading && !tree.error && tree.data && (
          <ul className="space-y-3">
            {tree.data.scenarios.map((s) => (
              <li key={s.key} className="rounded border border-ink-800 p-3">
                <div className="flex items-center gap-3">
                  <span className="w-6 text-center text-sm font-semibold text-slate-400">
                    {s.key}
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-200">{s.label}</span>
                      <span className="text-sm font-semibold tabular text-slate-300">
                        {pct(s.probability, 0)}
                      </span>
                    </div>
                    <ProbBar p={s.probability} className="mt-1.5 w-full" />
                    <div className="mt-1.5 text-xs text-slate-600">{s.description}</div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
