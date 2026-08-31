import { api, DEFAULT_USER_ID } from '../api/client';
import {
  Badge,
  Card,
  EmptyState,
  ErrorBox,
  Loading,
  PageHeader,
  ProbBar,
  Stat,
} from '../components/ui';
import { pct, shortDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 51 节 Prediction History
 *
 *   默认必须同时展示：成功 / 失败 / 部分 / 无法判断
 *   禁止产品设计诱导只看「神预测」。
 */
export default function Timeline() {
  const hist = useAsync(() => api.history(DEFAULT_USER_ID), []);
  const items = hist.data?.items ?? [];

  const full = items.filter((i) => i.outcome === 1).length;
  const partial = items.filter((i) => i.outcome > 0 && i.outcome < 1).length;
  const none = items.filter((i) => i.outcome === 0).length;
  const meanBrier =
    items.length > 0 ? items.reduce((a, b) => a + b.brier, 0) / items.length : null;

  return (
    <div className="space-y-5">
      <PageHeader title="时间线" desc="全部已验证预测，按时间倒序。成功与失败同等展示。" />

      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="完全命中" value={full} tone="good" />
        <Stat label="部分命中" value={partial} tone="warn" />
        <Stat label="未命中" value={none} tone="bad" />
        <Stat
          label="平均 Brier"
          value={meanBrier != null ? meanBrier.toFixed(3) : '—'}
          hint="概率质量，越低越好"
        />
      </div>

      <Card
        title="全部结果"
        subtitle="第 51 节：不得隐藏失败预测；命中率只是直观数据，质量以概率评分与校准为准"
      >
        {hist.loading && <Loading />}
        {hist.error && <ErrorBox message={hist.error} />}
        {!hist.loading && !hist.error && items.length === 0 && (
          <EmptyState>还没有已验证的预测。先去「验证」页提交结果。</EmptyState>
        )}

        <ul className="divide-y divide-line">
          {items.map((it) => (
            <li
              key={it.prediction_id}
              className="row-hover -mx-2 flex items-center gap-4 rounded-lg px-2 py-2.5"
            >
              <div className="w-28 shrink-0 text-xs text-t4">
                {shortDateTime(it.judged_at)}
              </div>

              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-t1">{it.event_type}</div>
                <div className="mt-1 flex items-center gap-2">
                  <ProbBar p={it.probability} className="w-28" />
                  <span className="text-xs tabular text-t2">
                    {pct(it.probability)}
                  </span>
                  {it.null_probability != null && (
                    <span className="text-[11px] text-t4">
                      Null {pct(it.null_probability)}
                    </span>
                  )}
                </div>
              </div>

              <div className="w-28 shrink-0 text-right">
                <Badge
                  tone={
                    it.outcome === 1 ? 'good' : it.outcome > 0 ? 'warn' : 'bad'
                  }
                >
                  {it.outcome === 1
                    ? '命中'
                    : it.outcome > 0
                      ? `部分 ${pct(it.outcome)}`
                      : '未命中'}
                </Badge>
              </div>

              <div className="w-20 shrink-0 text-right text-xs tabular text-t3">
                BS {it.brier.toFixed(3)}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
