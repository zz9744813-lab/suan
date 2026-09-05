import { api, DEFAULT_USER_ID } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, Stat } from '../components/ui';
import { RELIABILITY_COLOR, RELIABILITY_LABEL, num, pct } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 26 节 Personal Reliability Matrix
 * 第 77 节 层级可靠度
 * 第 79 节 模型版本管理
 * 第 84 节 North Star Metric：相对 Null Model 的 predictive skill
 *
 * 注意：矩阵里保存的是「相对 Null Model 的 skill」，不是命中率。
 */

function MatrixTable({
  title,
  rows,
  keyLabel,
}: {
  title: string;
  rows: {
    key: string;
    system?: string;
    domain?: string;
    time_scale?: string;
    sample_size: number;
    skill: number | null;
    brier: number | null;
    reliability: string;
    note?: string;
  }[];
  keyLabel: (r: { system?: string; domain?: string; time_scale?: string }) => string;
}) {
  if (rows.length === 0) return <EmptyState>暂无数据</EmptyState>;
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-t2">{title}</div>
      <table className="w-full text-xs">
        <thead className="text-t4">
          <tr className="border-b border-line">
            <th className="py-1 text-left">维度</th>
            <th className="py-1 text-right">样本</th>
            <th className="py-1 text-right">增益</th>
            <th className="py-1 text-right">误差</th>
            <th className="py-1 text-right">可靠度</th>
          </tr>
        </thead>
        <tbody className="tabular text-t2">
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-line">
              <td className="py-1">{keyLabel(r)}</td>
              <td className="py-1 text-right">{r.sample_size}</td>
              <td
                className={`py-1 text-right ${(r.skill ?? 0) > 0 ? 'text-jade-400' : (r.skill ?? 0) < 0 ? 'text-cinnabar-400' : ''}`}
              >
                {r.skill != null ? pct(r.skill, 1) : '—'}
              </td>
              <td className="py-1 text-right">{r.brier != null ? num(r.brier) : '—'}</td>
              <td className={`py-1 text-right ${RELIABILITY_COLOR[r.reliability] ?? ''}`}>
                {r.note ? r.note : RELIABILITY_LABEL[r.reliability] ?? r.reliability}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SYSTEM_LABEL: Record<string, string> = {
  ziwei: '紫微',
  bazi: '八字',
  qimen: '奇门',
  liuyao: '六爻',
  meihua: '梅花',
  zhouyi: '周易',
  palm: '掌纹',
  face: '面相',
  reality: '现实',
  null: 'Null 基线',
};

const DOMAIN_LABEL: Record<string, string> = {
  career: '职业', money: '财务', study: '学习', social: '社交',
  relationship: '关系', travel: '出行', project: '项目', habit: '习惯',
  purchase: '消费', communication: '沟通', schedule: '日程',
  unexpected_event: '意外',
};

const SCALE_LABEL: Record<string, string> = {
  day: '日', week: '周', month: '月', year: '年',
};

export default function Models() {
  const rel = useAsync(() => api.reliability(DEFAULT_USER_ID), []);
  const overall = useAsync(() => api.overall(DEFAULT_USER_ID), []);

  return (
    <div className="space-y-5">
      <PageHeader
        title="模型"
        desc="各术式、各领域的相对预测能力。这里保存的是「相对 Null Model 的 skill」，不是命中率。"
      />

      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="预测误差"
          value={overall.data ? num(overall.data.brier) : '—'}
          hint="Brier 评分 · 越低越好"
        />
        <Stat
          label="相对基线增益"
          value={
            overall.data?.skill_score != null ? pct(overall.data.skill_score, 1) : '—'
          }
          tone={(overall.data?.skill_score ?? 0) > 0 ? 'good' : 'bad'}
          hint="Skill vs Null · 第 84 节北极星指标"
        />
        <Stat
          label="判断锐度"
          value={overall.data ? num(overall.data.sharpness, 4) : '—'}
          hint="Sharpness · 离 0.5 越远越果断"
        />
      </div>

      <Card
        title="个人可靠度矩阵"
        subtitle="第 26 节：系统应允许得到「不好听」的结果 —— 若某术式无贡献，就显示无贡献"
      >
        {rel.loading && <Loading />}
        {rel.error && <ErrorBox message={rel.error} />}
        {!rel.loading && !rel.error && rel.data && (
          <div className="space-y-5">
            <MatrixTable
              title="按术式系统"
              rows={rel.data.by_system}
              keyLabel={(r) => SYSTEM_LABEL[r.system ?? ''] ?? (r.system ?? '—')}
            />
            <MatrixTable
              title="按领域"
              rows={rel.data.by_domain}
              keyLabel={(r) => DOMAIN_LABEL[r.domain ?? ''] ?? (r.domain ?? '—')}
            />
            <MatrixTable
              title="按时间尺度"
              rows={rel.data.by_time_scale}
              keyLabel={(r) => SCALE_LABEL[r.time_scale ?? ''] ?? (r.time_scale ?? '—')}
            />

            <div>
              <div className="mb-1.5 text-xs font-medium text-t2">
                融合权重（由实证增益学习得到）
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(rel.data.fusion_weights).map(([k, v]) => (
                  <Badge key={k} tone={v > 1 ? 'good' : v < 1 ? 'bad' : 'default'}>
                    {SYSTEM_LABEL[k] ?? k} ×{v.toFixed(2)}
                  </Badge>
                ))}
                {Object.keys(rel.data.fusion_weights).length === 0 && (
                  <span className="text-xs text-t4">
                    尚无足够样本，全部按 1.0（不惩罚也不奖励，第 77 节弱先验）
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
