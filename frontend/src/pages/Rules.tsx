import { useState } from 'react';

import { api } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader } from '../components/ui';
import { DOMAIN_LABEL, SCALE_LABEL } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 25 节 Rule Registry
 *
 *   每个传统规则必须有唯一 ID，以后可以统计：
 *       BAZI-R-00427
 *       调用次数：214
 *       平均增益：+0.018
 *       职业预测：有效 / 关系预测：无效
 *       日级：无效 / 月级：有效
 *
 * 第 7 节原则：新增术式必须通过独立验证，
 *             不允许因为「传统上有名」就获得高权重。
 */
export default function Rules() {
  const [status, setStatus] = useState('active');
  const rules = useAsync(() => api.rules(status), [status]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="规则"
        desc="每条传统规则都有唯一 ID，长期统计其在各领域、各时间尺度上的真实增益。"
        right={
          <div className="inline-flex gap-0.5 rounded-lg border border-line bg-panel p-0.5">
            {['active', 'shadow', 'deprecated', 'rejected'].map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`btn-press rounded-md px-2.5 py-1 text-xs transition ${
                  status === s
                    ? 'bg-panel text-gt shadow-card'
                    : 'text-t4 hover:text-t2'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        }
      />

      <Card title={`规则清单（${status}）`}>
        {rules.loading && <Loading />}
        {rules.error && <ErrorBox message={rules.error} />}
        {!rules.loading && !rules.error && (rules.data?.items.length ?? 0) === 0 && (
          <EmptyState>
            暂无已登记规则。规则由各术式 Agent 在产出 Signal 时通过 rule_ids 引用，
            <br />
            骨架阶段八字模块会生成形如 <code className="text-t2">BAZI-R-官-career</code> 的规则 ID。
          </EmptyState>
        )}

        {(rules.data?.items.length ?? 0) > 0 && (
          <table className="w-full text-xs">
            <thead className="text-t4">
              <tr className="border-b border-line">
                <th className="py-1.5 text-left">规则 ID</th>
                <th className="py-1.5 text-left">流派</th>
                <th className="py-1.5 text-left">领域</th>
                <th className="py-1.5 text-left">支持尺度</th>
                <th className="py-1.5 text-right">版本</th>
              </tr>
            </thead>
            <tbody className="text-t2">
              {rules.data?.items.map((r) => (
                <tr key={r.rule_id} className="border-b border-line">
                  <td className="py-1.5 font-mono text-t1">{r.rule_id}</td>
                  <td className="py-1.5">
                    <Badge>{r.school}</Badge>
                  </td>
                  <td className="py-1.5">
                    {r.domains.map((d) => DOMAIN_LABEL[d] ?? d).join('、') || '—'}
                  </td>
                  <td className="py-1.5">
                    {r.supported_windows.map((w) => SCALE_LABEL[w] ?? w).join('、') || '—'}
                  </td>
                  <td className="py-1.5 text-right tabular">{r.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
