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
  ProgressBar,
  Segmented,
  Stat,
} from '../components/ui';
import {
  DOMAIN_LABEL,
  SCALE_LABEL,
  STATUS_LABEL,
  cleanDescription,
  edgeClass,
  edgeText,
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

/**
 * 校准旅程：三阶段（基线校准 → 信号实证 → 正式预测）。
 * 冷启动校准分层方案的对外呈现 —— 系统在哪个阶段、为什么、还差多少，全部透明。
 */
type Phase = 'cold' | 'explore' | 'formal';

function CalibrationJourney({
  phase,
  calibrated,
  minCalibration,
  minFormal,
}: {
  phase: Phase;
  calibrated: number;
  minCalibration: number;
  minFormal: number;
}) {
  const steps: { key: Phase; label: string; desc: string; target: number | null }[] = [
    { key: 'cold', label: '基线校准', desc: '建立真实频率基线', target: minCalibration },
    { key: 'explore', label: '信号实证', desc: '术式弱先验参与留痕', target: minFormal },
    { key: 'formal', label: '正式预测', desc: '可靠度权重已实证', target: null },
  ];
  const idx = phase === 'cold' ? 0 : phase === 'explore' ? 1 : 2;
  const target = steps[idx].target;

  return (
    <div>
      <div className="flex items-stretch">
        {steps.map((s, i) => {
          const done = i < idx;
          const current = i === idx;
          return (
            <div key={s.key} className="flex min-w-0 flex-1 items-center">
              <div className="flex min-w-[86px] flex-1 flex-col items-center gap-1.5 text-center">
                <span
                  className={`flex h-7 w-7 items-center justify-center rounded-full border text-[10px] font-semibold transition-all duration-500 ${
                    done
                      ? 'border-gilt-400 bg-gilt-500/15 text-gt'
                      : current
                        ? 'status-dot border-gilt-400 bg-gilt-500/20 text-gt shadow-[0_0_12px_-2px_rgba(217,185,106,0.6)]'
                        : 'border-line bg-panel text-t5'
                  }`}
                >
                  {done ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                      <path d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </span>
                <div>
                  <div
                    className={`text-xs font-medium transition-colors duration-300 ${
                      current ? 'text-t1' : done ? 'text-t2' : 'text-t5'
                    }`}
                  >
                    {s.label}
                  </div>
                  <div className="mt-0.5 hidden text-[10px] text-t5 md:block">{s.desc}</div>
                </div>
              </div>
              {i < steps.length - 1 && (
                <div className="relative mx-1 h-px flex-1 bg-line">
                  <div
                    className={`absolute inset-y-0 left-0 bg-gilt-500/60 transition-all duration-700 ${
                      done ? 'w-full' : 'w-0'
                    }`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {target != null && (
        <div className="mt-4">
          <div className="mb-1.5 flex items-baseline justify-between text-xs">
            <span className="text-t3">
              {phase === 'cold'
                ? '已验证样本（Null 基线校准中，术式尚未参与）'
                : '已验证样本（术式弱先验参与，积累实证中）'}
            </span>
            <span className="tabular font-semibold text-t1">
              {calibrated}
              <span className="text-t4">/{target}</span>
            </span>
          </div>
          <ProgressBar value={calibrated} max={target} />
        </div>
      )}
    </div>
  );
}

export default function Future() {
  const [scale, setScale] = useState<(typeof SCALES)[number]['key']>('day');
  const [generating, setGenerating] = useState(false);
  const [notes, setNotes] = useState<string[] | null>(null);
  const [notesOpen, setNotesOpen] = useState(true);
  const [runDone, setRunDone] = useState(false);

  const preds = useAsync(() => api.listPredictions(DEFAULT_USER_ID), []);
  const overall = useAsync(() => api.overall(DEFAULT_USER_ID), []);
  const due = useAsync(() => api.duePredictions(DEFAULT_USER_ID), []);
  const health = useAsync(() => api.health(), []);
  const tree = useAsync(() => api.futureTree(DEFAULT_USER_ID), []);
  const meta = useAsync(() => api.meta(), []);

  // 校准阶段门槛：三阶段（cold 基线校准 → explore 信号实证 → formal 正式预测）
  const calibration = (
    meta.data as
      | {
          calibration?: {
            min_calibration_samples?: number;
            min_formal_samples?: number;
          };
        }
      | undefined
  )?.calibration;
  const minCalibration = calibration?.min_calibration_samples ?? 5;
  const minFormal = calibration?.min_formal_samples ?? 20;
  const calibratedCount = overall.data?.sample_size ?? 0;
  const phase: Phase =
    calibratedCount < minCalibration
      ? 'cold'
      : calibratedCount < minFormal
        ? 'explore'
        : 'formal';
  const phaseTarget = phase === 'cold' ? minCalibration : minFormal;
  const researching = phase !== 'formal';

  const visible = (preds.data?.items ?? []).filter(
    (p) => p.time_scale === scale || scale === 'day',
  );
  const research = visible.filter((p) => p.status === 'RESEARCH');
  const formal = visible.filter((p) => p.status !== 'RESEARCH');

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

  const renderRow = (p: (typeof visible)[number], isResearch = false) => (
    <li key={p.prediction_id} className="row-hover rounded-lg border border-line p-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-t1">{cleanDescription(p.description, p.event_type)}</span>
            <Badge>{DOMAIN_LABEL[p.domain] ?? p.domain}</Badge>
            <Badge tone="info">{SCALE_LABEL[p.time_scale]}</Badge>
            {p.visibility_mode === 'HIDDEN' && <Badge tone="warn">隐藏模式</Badge>}
          </div>
          <div className="mt-1 text-xs text-t4">
            {p.event_type} · 窗口 {shortDate(p.window[0])} ~ {shortDate(p.window[1])}
            {p.verification_due_at && ` · 验证截止 ${shortDateTime(p.verification_due_at)}`}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <ProbBar p={p.probability} className="w-40" />
            <span className="text-sm font-semibold tabular text-t1">{pct(p.probability)}</span>
            {p.null_probability != null && (
              <>
                <span className="text-xs text-t4">Null 基线 {pct(p.null_probability)}</span>
                <span
                  className={`text-xs font-medium ${edgeClass(p.probability, p.null_probability)}`}
                  title="预测概率相对 Null 基线的差值：正值=比随机强，负值=比随机还差"
                >
                  {edgeText(p.probability, p.null_probability)}
                </span>
              </>
            )}
          </div>
          {isResearch && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-amber-400/90">
              <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
              <span>
                {phase === 'explore'
                  ? '研究样本（实证期）：术式信号以弱先验参与并完整留痕，验证后将转化为各术式的可靠度实证。尚不代表预测力。'
                  : '研究样本（冷启动）：术式信号未参与，概率 = Null 基线。用于启动校准闭环、积累验证数据，不代表预测力。'}
              </span>
            </div>
          )}
        </div>
        <div className="shrink-0 text-right">
          <Badge
            tone={
              p.status === 'VERIFIED'
                ? 'good'
                : p.status === 'RESEARCH'
                  ? 'warn'
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
  );

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
              {generating
                ? phase === 'formal'
                  ? '生成中，LLM 正在评审候选…'
                  : '生成中，秒级完成…'
                : '生成预测'}
            </PrimaryButton>
          </>
        }
      />

      {/* 闭环流水线：页面视觉锚点 */}
      <Card
        title="预测闭环"
        subtitle={
          generating
            ? phase === 'formal'
              ? '正在逐站推进，LLM 评审入选候选（已并发，约一两分钟）…'
              : '研究期全程确定性计算，不依赖 LLM，秒级完成…'
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

      {/* 校准旅程（研究期显示）：三阶段可感知，诚实且可预期 */}
      {researching && (
        <Card
          title="校准旅程"
          subtitle="系统在当前阶段的每次克制，都是为了让「正式预测」四个字有实证支撑"
          right={<Badge tone="warn">{phase === 'cold' ? '冷启动' : '信号实证'}</Badge>}
        >
          <CalibrationJourney
            phase={phase}
            calibrated={calibratedCount}
            minCalibration={minCalibration}
            minFormal={minFormal}
          />
        </Card>
      )}

      {/* 尺度切换：分段控件 */}
      <Segmented options={SCALES} value={scale} onChange={setScale} />

      {/* 概览指标 */}
      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="待验证" value={due.data?.count ?? '—'} hint="到期需用户确认" />
        <Stat
          label={researching ? '校准进度' : '校准样本'}
          value={`${calibratedCount}/${phaseTarget}`}
          hint={
            phase === 'cold'
              ? '基线校准中 · 达标后进入信号实证'
              : phase === 'explore'
                ? '信号实证中 · 达标后解锁正式预测'
                : '已解锁正式预测'
          }
          tone={phase === 'formal' ? 'good' : 'warn'}
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

      {/* 研究期研究样本 */}
      {researching && (
        <Card
          title="研究样本"
          subtitle={
            phase === 'cold'
              ? `校准进度 ${calibratedCount}/${minCalibration}：尚未积累足够验证数据，术式信号未参与预测。以下样本用于启动校准闭环，验证后系统才会学会真正预测。`
              : `实证进度 ${calibratedCount}/${minFormal}：术式信号以弱先验权重参与融合并完整留痕，每条验证都在为对应术式积累实证。`
          }
          right={
            <Badge tone="warn">{phase === 'cold' ? '冷启动模式' : '实证研究模式'}</Badge>
          }
        >
          {preds.loading && <Loading />}
          {preds.error && <ErrorBox message={preds.error} />}
          {!preds.loading && !preds.error && research.length === 0 && (
            <EmptyState>
              暂无研究样本。
              <br />
              点击右上角「生成预测」，系统会从候选事件里挑出最值得观察的几件，
              作为研究样本冻结，供你在「验证」页填结果。
            </EmptyState>
          )}
          <ul className="stagger space-y-3">{research.map((p) => renderRow(p, true))}</ul>
        </Card>
      )}

      {/* 正式冻结预测 */}
      <Card
        title="正式冻结预测"
        subtitle="只有通过对抗性 Gate 并获得预算额度的预测才会出现在这里"
      >
        {preds.loading && <Loading />}
        {preds.error && <ErrorBox message={preds.error} />}
        {!preds.loading && !preds.error && formal.length === 0 && (
          <EmptyState>
            {researching ? (
              <>
                还没有正式预测。
                <br />
                {phase === 'cold'
                  ? '系统处于基线校准期：术式信号未经实证、不参与融合，只产出「研究样本」（见上方）。'
                  : '系统处于信号实证期：术式以弱先验参与融合并留痕，但暂不产出正式预测，只产出「研究样本」。'}
                <br />
                <span className="text-t4">
                  （C-006 诚实原则：术数不比随机强时，系统必须承认它没有预测力，
                  而不是硬造噪声预测。累计 {minFormal} 条验证样本后自动解锁正式预测。）
                </span>
              </>
            ) : (
              <>
                当前没有正式预测。
                <br />
                系统只在「术数/现实信号显著超过随机基线」时才冻结预测——
                如果今天没找到有预测力的事件，会诚实放弃，而不是硬造噪声预测。
                <br />
                <span className="text-t4">
                  （这是 C-006 诚实原则：若术数不比随机强，系统必须承认它没有贡献。）
                </span>
              </>
            )}
          </EmptyState>
        )}
        <ul className="stagger space-y-3">{formal.map((p) => renderRow(p))}</ul>
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
