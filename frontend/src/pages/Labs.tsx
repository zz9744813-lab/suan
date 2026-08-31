import ReactECharts from 'echarts-for-react';
import { useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, Stat, inputCls } from '../components/ui';
import { num, pct } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 52 节 Accuracy Lab
 * 第 19.3 节 Calibration Curve
 * 第 33 节 Ablation Test
 * 第 20 节 对抗性 Gate 手动测试器
 */

/** 读取当前主题，返回该主题下的 ECharts 轴/网格颜色（暗色底用深线，浅色底用浅线）。 */
function chartColors() {
  const dark = document.documentElement.dataset.theme === 'dark';
  return {
    axisLine: dark ? '#2f3745' : '#cbd5e1',
    axisLabel: dark ? '#64748b' : '#5d6b84',
    splitLine: dark ? '#1c2230' : '#e2e8f0',
    reference: dark ? '#475569' : '#94a3b8',
  };
}

function CalibrationChart({
  bins,
}: {
  bins: { bin: string; n: number; predicted: number; actual: number }[];
}) {
  if (bins.length === 0) return <EmptyState>样本不足，暂无法绘制校准曲线。</EmptyState>;

  const c = chartColors();
  const option = {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    tooltip: {
      trigger: 'item',
      formatter: (p: { data: number[] }) =>
        `预测 ${(p.data[0] * 100).toFixed(0)}% / 实际 ${(p.data[1] * 100).toFixed(0)}%`,
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 1,
      name: '预测概率',
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.axisLabel, fontSize: 11 },
      splitLine: { lineStyle: { color: c.splitLine } },
      nameTextStyle: { color: c.axisLabel, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      name: '实际发生率',
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.axisLabel, fontSize: 11 },
      splitLine: { lineStyle: { color: c.splitLine } },
      nameTextStyle: { color: c.axisLabel, fontSize: 11 },
    },
    series: [
      {
        // 理想校准线：预测 = 实际
        type: 'line',
        data: [
          [0, 0],
          [1, 1],
        ],
        symbol: 'none',
        lineStyle: { color: c.reference, type: 'dashed', width: 1 },
        silent: true,
      },
      {
        type: 'scatter',
        data: bins.map((b) => [b.predicted, b.actual]),
        symbolSize: (d: number[]) => 10 + Math.sqrt(d[2] ?? 1) * 2,
        itemStyle: { color: '#22c55e' },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 300 }} notMerge />;
}

function GateTester() {
  const [desc, setDesc] = useState('最近可能有些变化，需要注意人际关系。');
  const [criteria, setCriteria] = useState('可能发生变化');
  const [res, setRes] = useState<import('../types').GateTestResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.gateTest({
        description: desc,
        event_type: 'career.unexpected_task',
        probability: 0.55,
        null_probability: 0.52,
        success_criteria: criteria ? [criteria] : [],
        failure_criteria: [],
      });
      setRes(r);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="对抗性 Gate 测试器"
      subtitle="第 20 节：14 种攻击全部为确定性实现，不依赖 LLM"
    >
      <div className="space-y-2">
        <input
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="预测描述"
          className={`w-full ${inputCls}`}
        />
        <input
          value={criteria}
          onChange={(e) => setCriteria(e.target.value)}
          placeholder="成功标准"
          className={`w-full ${inputCls}`}
        />
        <button
          onClick={run}
          disabled={busy}
          className="btn-press rounded-lg bg-t1 px-3.5 py-1.5 text-xs font-semibold text-page hover:opacity-85 disabled:opacity-50"
        >
          {busy ? '检测中…' : '跑一遍 Gate'}
        </button>
      </div>

      {res && (
        <div className="mt-3">
          <div className="mb-2">
            决策：
            <Badge
              tone={
                res.decision === 'PASS'
                  ? 'good'
                  : res.decision === 'EXPERIMENTAL'
                    ? 'warn'
                    : 'bad'
              }
            >
              {res.decision}
            </Badge>
          </div>
          <ul className="space-y-1">
            {res.attacks.map((a) => (
              <li key={a.attack} className="flex items-start gap-2 text-xs">
                <Badge
                  tone={
                    a.verdict === 'PASS'
                      ? 'good'
                      : a.verdict === 'FAIL'
                        ? 'bad'
                        : a.verdict === 'WARN'
                          ? 'warn'
                          : 'default'
                  }
                >
                  {a.verdict}
                </Badge>
                <span className="w-56 shrink-0 text-t2">{a.attack}</span>
                <span className="text-t4">{a.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export default function Labs() {
  const overall = useAsync(() => api.overall(DEFAULT_USER_ID), []);
  const calib = useAsync(() => api.calibration(DEFAULT_USER_ID), []);
  const ablation = useAsync(() => api.ablation(DEFAULT_USER_ID), []);

  const o = overall.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title="实验室"
        desc="概率质量、校准、与 Null Model 的对比，以及消融实验。"
      />

      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="样本量" value={o?.sample_size ?? '—'} />
        <Stat label="Brier" value={o ? num(o.brier) : '—'} hint="越低越好" />
        <Stat label="Log Loss" value={o ? num(o.log_loss) : '—'} hint="惩罚极端错误" />
        <Stat
          label="Sharpness"
          value={o ? num(o.sharpness, 4) : '—'}
          hint="第19.4节：永远50%则为0"
        />
        <Stat
          label="Skill vs Null"
          value={o?.skill_score != null ? pct(o.skill_score, 1) : '—'}
          hint=">0 才说明超过基线"
          tone={(o?.skill_score ?? 0) > 0 ? 'good' : 'bad'}
        />
      </div>

      {o && o.sample_size > 0 && (
        <Card
          title="可信区间与过度自信"
          subtitle="第 78 节小样本保护 · 第 19.3 节校准"
          right={
            <Badge tone={o.reliability === 'high' ? 'good' : o.reliability === 'medium' ? 'warn' : 'default'}>
              {o.reliability === 'high' ? '样本可靠' : o.reliability === 'medium' ? '样本中等' : '样本不足'}
            </Badge>
          }
        >
          <div className="grid gap-3 text-xs md:grid-cols-3">
            <div>
              <div className="text-t3">观测发生率</div>
              <div className="mt-1 text-lg tabular text-t1">{pct(o.observed_rate, 1)}</div>
              <div className="mt-0.5 text-t4">
                95% CI [{pct(o.ci[0], 1)}, {pct(o.ci[1], 1)}]
              </div>
            </div>
            <div>
              <div className="text-t3">平均预测概率</div>
              <div className="mt-1 text-lg tabular text-t1">{pct(o.mean_probability, 1)}</div>
            </div>
            <div>
              <div className="text-t3">过度自信指数</div>
              <div
                className={`mt-1 text-lg tabular ${(o.overconfidence ?? 0) > 0.05 ? 'text-cinnabar-400' : 'text-t1'}`}
              >
                {(o.overconfidence ?? 0) > 0 ? '+' : ''}
                {o.overconfidence != null ? o.overconfidence.toFixed(3) : '—'}
              </div>
              <div className="mt-0.5 text-t4">正值 = 模型过度自信</div>
            </div>
          </div>
        </Card>
      )}

      <Card
        title="校准曲线"
        subtitle="第 19.3 节：所有标 70% 的预测，实际发生率应接近 70%"
      >
        {calib.loading && <Loading />}
        {calib.error && <ErrorBox message={calib.error} />}
        {!calib.loading && !calib.error && <CalibrationChart bins={calib.data?.bins ?? []} />}
        {calib.data && calib.data.bins.length > 0 && (
          <table className="mt-3 w-full text-xs">
            <thead className="text-t4">
              <tr className="border-b border-line">
                <th className="py-1 text-left">分桶</th>
                <th className="py-1 text-right">样本</th>
                <th className="py-1 text-right">预测</th>
                <th className="py-1 text-right">实际</th>
                <th className="py-1 text-right">偏差</th>
              </tr>
            </thead>
            <tbody className="tabular text-t2">
              {calib.data.bins.map((b) => (
                <tr key={b.bin} className="border-b border-line">
                  <td className="py-1">{b.bin}</td>
                  <td className="py-1 text-right">{b.n}</td>
                  <td className="py-1 text-right">{pct(b.predicted, 1)}</td>
                  <td className="py-1 text-right">{pct(b.actual, 1)}</td>
                  <td
                    className={`py-1 text-right ${Math.abs(b.gap) > 0.1 ? 'text-cinnabar-400' : ''}`}
                  >
                    {b.gap > 0 ? '+' : ''}
                    {(b.gap * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card
        title="消融实验"
        subtitle="第 33 节：判断每个模块到底有没有贡献。系统允许得到「不好听」的结果"
      >
        {ablation.loading && <Loading />}
        {ablation.error && <ErrorBox message={ablation.error} />}
        {!ablation.loading && !ablation.error && (
          <EmptyState>{ablation.data?.note ?? '尚无数据'}</EmptyState>
        )}
      </Card>

      <GateTester />
    </div>
  );
}
