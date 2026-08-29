import { useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import { Badge, Card, EmptyState, ErrorBox, Loading } from '../components/ui';
import { shortDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 50 节 Verification Inbox
 * 第 59 节：到期主动进入 VERIFY_REQUIRED；用户暂不回复则 WAITING_USER，
 *           不能自动判成功。
 * 第 60 节：支持自然语言回复；可能对应多条预测时必须要求明确，不能强行命中。
 */
const QUICK = [
  { key: 'A', label: '发生', tone: 'good' as const },
  { key: 'B', label: '未发生', tone: 'bad' as const },
  { key: 'C', label: '部分发生', tone: 'warn' as const },
  { key: 'D', label: '无法判断', tone: 'default' as const },
];

export default function Verify() {
  const due = useAsync(() => api.duePredictions(DEFAULT_USER_ID), []);
  const [reply, setReply] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, string>>({});

  const submit = async (pid: string, quick?: string) => {
    setBusy(pid);
    try {
      const r = await api.verify(pid, reply[pid], quick);
      if (r.needs_confirmation) {
        // 第 20.13 节：三方 Judge 分歧 → 转人工，不强行判定
        setResult((s) => ({
          ...s,
          [pid]: `三方 Judge 分歧 ${r.disagreement.toFixed(2)}，已标记待人工确认（不强行判定）`,
        }));
      } else {
        setResult((s) => ({
          ...s,
          [pid]: `判定 ${(r.outcome * 100).toFixed(0)}%（置信 ${(r.confidence * 100).toFixed(0)}%）`,
        }));
      }
      due.reload();
    } catch (e) {
      setResult((s) => ({ ...s, [pid]: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusy(null);
    }
  };

  const items = due.data?.items ?? [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">验证</h1>
        <p className="mt-1 text-xs text-slate-500">
          到期的预测会主动出现在这里。成败一视同仁，系统不会只挑算准的给你看。
        </p>
      </header>

      <Card title={`待验证 ${due.data?.count ?? 0}`} subtitle="第 59 节：到期主动提醒，不自动判成功">
        {due.loading && <Loading />}
        {due.error && <ErrorBox message={due.error} />}
        {!due.loading && !due.error && items.length === 0 && (
          <EmptyState>当前没有到期的预测。</EmptyState>
        )}

        <ul className="space-y-4">
          {items.map((it) => (
            <li key={it.prediction_id} className="rounded border border-ink-800 p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="text-sm text-slate-200">{it.description}</div>
                  <div className="mt-1 text-xs text-slate-600">
                    {it.event_type} · 窗口 {shortDateTime(it.window[0])} ~{' '}
                    {shortDateTime(it.window[1])}
                  </div>
                </div>
                <Badge>{it.probability != null ? `${(it.probability * 100).toFixed(0)}%` : '—'}</Badge>
              </div>

              <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
                <div className="rounded bg-ink-900 p-2">
                  <div className="mb-1 font-medium text-jade-400">成功标准</div>
                  <ul className="space-y-0.5 text-slate-400">
                    {it.success_criteria.map((c, i) => (
                      <li key={i}>· {c}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded bg-ink-900 p-2">
                  <div className="mb-1 font-medium text-cinnabar-400">失败标准</div>
                  <ul className="space-y-0.5 text-slate-400">
                    {it.failure_criteria.map((c, i) => (
                      <li key={i}>· {c}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {QUICK.map((q) => (
                  <button
                    key={q.key}
                    disabled={busy === it.prediction_id}
                    onClick={() => submit(it.prediction_id, q.key)}
                    className="rounded border border-ink-700 px-2.5 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:opacity-50"
                  >
                    {q.label}
                  </button>
                ))}
              </div>

              <div className="mt-3 flex gap-2">
                <input
                  value={reply[it.prediction_id] ?? ''}
                  onChange={(e) =>
                    setReply((s) => ({ ...s, [it.prediction_id]: e.target.value }))
                  }
                  placeholder="也可以直接描述今天发生了什么…"
                  className="flex-1 rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
                />
                <button
                  disabled={busy === it.prediction_id || !reply[it.prediction_id]}
                  onClick={() => submit(it.prediction_id)}
                  className="rounded bg-slate-200 px-3 py-1.5 text-xs font-medium text-ink-950 disabled:opacity-40"
                >
                  提交
                </button>
              </div>

              {result[it.prediction_id] && (
                <div className="mt-2 text-xs text-sky-400">{result[it.prediction_id]}</div>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
