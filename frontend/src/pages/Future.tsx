import { useEffect, useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import {
  Badge,
  Card,
  EmptyState,
  ErrorBox,
  Loading,
  PageHeader,
  PrimaryButton,
  ProbBar,
  Stat,
} from '../components/ui';
import {
  DOMAIN_LABEL,
  SCALE_LABEL,
  STATUS_LABEL,
  num,
  pct,
  shortDate,
  shortDateTime,
} from '../lib/format';
import { useAsync } from '../lib/useAsync';

const SCALES = [
  { key: 'day', label: '今日' },
  { key: 'week', label: '7 天' },
  { key: 'month', label: '30 天' },
  { key: 'year', label: '90 天' },
] as const;

/** 预测闭环七步（对应系统流水线） */
const PIPELINE = [
  { key: 'scan', label: '扫描', desc: '候选事件' },
  { key: 'blind', label: '盲审', desc: '去标识评分' },
  { key: 'fuse', label: '融合', desc: '多引擎加权' },
  { key: 'gate', label: '审查', desc: '对抗性 Gate' },
  { key: 'budget', label: '预算', desc: '额度竞争' },
  { key: 'freeze', label: '冻结', desc: 'SHA-256 封账' },
  { key: 'verify', label: '验证', desc: '现实检验' },
];

/**
 * 闭环流水线可视化 —— 页面的视觉锚点。
 * 生成中：逐步点亮的进行态；空闲：静态展示流程。
 */
function PipelineSteps({ active, done }: { active: boolean; done: boolean }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!active) return;
    setStep(0);
    const t = setInterval(() => setStep((s) => (s + 1) % PIPELINE.length), 900);
    return () => clearInterval(t);
  }, [active]);

  return (
    <div className="flex items-stretch gap-0 overflow-x-auto pb-1">
      {PIPELINE.map((p, i) => {
        const lit = active ? i <= step : done;
        const current = active && i === step;
        return (
          <div key={p.key} className="flex min-w-0 flex-1 items-center">
            <div className="flex min-w-[64px] flex-1 flex-col items-center gap-1.5 text-center">
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-full border text-[11px] font-semibold transition-all duration-500 ${
                  current
                    ? 'status-dot border-gilt-400 bg-gilt-500/20 text-gt'
                    : lit
                      ? 'border-gilt-500/50 bg-gilt-500/10 text-gt'
                      : 'border-line bg-panel text-t5'
                }`}
              >
                {i + 1}
              </span>
              <div>
                <div
                  className={`text-xs font-medium transition-colors duration-500 ${
                    lit ? 'text-t1' : 'text-t4'
                  }`}
                >
                  {p.label}
                </div>
                <div className="mt-0.5 text-[10px] text-t5">{p.desc}</div>
              </div>
            </div>
            {i < PIPELINE.length - 1 && (
              <div
                className={`mx-1 h-px w-4 shrink-0 transition-colors duration-500 md:w-6 ${
                  lit && i < step ? 'bg-gilt-500/50' : 'bg-panel'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function Future() {
  const [scale, setScale] = useState<string>('day');
  const [generating, setGenerating] = useState(false);
  const [notes, setNotes] = useState<string[] | null>(null);
  const [notesOpen, setNotesOpen] = useState(true);
  const [runDone, setRunDone] = useState(false);

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
    setRunDone(false);
    setNotes(null);
    setNotesOpen(true);
    try {
      const r = await api.generate(DEFAULT_USER_ID, scale, 20);
      setNotes([
        ...r.notes,
        ...r.rejected.map((x) => `拦截 ${x.event_type}（${x.decision}）：${x.reasons[0] ?? ''}`),
      ]);
      preds.reload();
      overall.reload();
      due.reload();
      setRunDone(true);
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
      <PageHeader
        title="未来"
        desc="系统主动生成预测并冻结，等待现实检验。候选不等于正式预测。"
        right={
          <>
            <Badge tone={engineOk > 0 ? 'good' : 'warn'}>
              引擎 {engineOk}/{engineTotal} 可用
            </Badge>
            <PrimaryButton onClick={generate} busy={generating}>
              {generating ? '生成中，约需一分钟…' : '生成预测'}
            </PrimaryButton>
          </>
        }
      />

      {/* 闭环流水线：页面视觉锚点 */}
      <Card
        title="预测闭环"
        subtitle={
          generating
            ? '正在逐站推进，LLM 评审约需一分钟…'
            : runDone
              ? '本轮闭环已跑完，以下为运行记录'
              : '每条正式预测都必须走完这七站'
        }
      >
        <PipelineSteps active={generating} done={runDone} />
      </Card>

      {notes && (
        <Card
          title={`本轮运行记录 · ${notes.length} 条`}
          subtitle="含被对抗性 Gate 拦截的候选"
          right={
            <button
              onClick={() => setNotesOpen((v) => !v)}
              className="btn-press text-xs text-t3 hover:text-t1"
            >
              {notesOpen ? '收起 ▲' : '展开 ▼'}
            </button>
          }
        >
          {notesOpen && (
            <ul className="stagger space-y-1 text-xs text-t2">
              {notes.map((n, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-gt">·</span>
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* 尺度切换：分段控件 */}
      <div className="inline-flex gap-0.5 rounded-lg border border-line bg-panel p-0.5">
        {SCALES.map((s) => (
          <button
            key={s.key}
            onClick={() => setScale(s.key)}
            className={`btn-press rounded-md px-3.5 py-1.5 text-xs font-medium tracking-wide ${
              scale === s.key
                ? 'bg-panel text-gt shadow-card'
                : 'text-t4 hover:text-t2'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 概览指标 */}
      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-4">
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
          value={overall.data ? num(overall.data.brier) : '—'}
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
        <ul className="stagger space-y-3">
          {visible.map((p) => (
            <li
              key={p.prediction_id}
              className="row-hover rounded-lg border border-line p-3"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-t1">{p.description}</span>
                    <Badge>{DOMAIN_LABEL[p.domain] ?? p.domain}</Badge>
                    <Badge tone="info">{SCALE_LABEL[p.time_scale]}</Badge>
                    {p.visibility_mode === 'HIDDEN' && (
                      <Badge tone="warn">隐藏模式</Badge>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-t4">
                    {p.event_type} · 窗口 {shortDate(p.window[0])} ~ {shortDate(p.window[1])}
                    {p.verification_due_at && ` · 验证截止 ${shortDateTime(p.verification_due_at)}`}
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <ProbBar p={p.probability} className="w-40" />
                    <span className="text-sm font-semibold tabular text-t1">
                      {pct(p.probability)}
                    </span>
                    {p.null_probability != null && (
                      <span className="text-xs text-t4">
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
                  <div
                    className="mt-1 font-mono text-[10px] text-t5"
                    title="冻结哈希前缀（防篡改）"
                  >
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
          <ul className="stagger space-y-3">
            {tree.data.scenarios.map((s) => (
              <li
                key={s.key}
                className="row-hover rounded-lg border border-line p-3"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-gilt-500/30 bg-gilt-500/10 text-sm font-semibold text-gt">
                    {s.key}
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-t1">{s.label}</span>
                      <span className="text-sm font-semibold tabular text-t1">
                        {pct(s.probability, 0)}
                      </span>
                    </div>
                    <ProbBar p={s.probability} className="mt-1.5 w-full" />
                    <div className="mt-1.5 text-xs text-t4">{s.description}</div>
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
