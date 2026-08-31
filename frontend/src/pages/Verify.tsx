import { useState } from 'react';

import { api, DEFAULT_USER_ID } from '../api/client';
import {
  Badge,
  Card,
  EmptyState,
  ErrorBox,
  Loading,
  PageHeader,
  inputCls,
} from '../components/ui';
import { cleanDescription, shortDateTime } from '../lib/format';
import { useAsync } from '../lib/useAsync';

/**
 * 第 50 节 Verification Inbox
 * 第 59 节：到期主动进入 VERIFY_REQUIRED；用户暂不回复则 WAITING_USER，
 *           不能自动判成功。
 * 第 60 节：支持自然语言回复；可能对应多条预测时必须要求明确，不能强行命中。
 */
const QUICK = [
  { key: 'A', label: '发生', cls: 'border-jade-500/40 text-jade-400 hover:bg-jade-500/15' },
  { key: 'B', label: '未发生', cls: 'border-cinnabar-500/40 text-cinnabar-400 hover:bg-cinnabar-500/15' },
  { key: 'C', label: '部分发生', cls: 'border-amber-500/40 text-amber-400 hover:bg-amber-500/15' },
  { key: 'D', label: '无法判断', cls: 'border-ink-600 text-t2 hover:bg-panel' },
];

export default function Verify() {
  const due = useAsync(() => api.duePredictions(DEFAULT_USER_ID), []);
  const [reply, setReply] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, { text: string; ok: boolean }>>({});

  const submit = async (pid: string, quick?: string) => {
    setBusy(pid);
    try {
      const r = await api.verify(pid, reply[pid], quick);
      if (r.needs_confirmation) {
        // 第 20.13 节：三方 Judge 分歧 → 转人工，不强行判定
        setResult((s) => ({
          ...s,
          [pid]: {
            text: `三方 Judge 分歧 ${r.disagreement.toFixed(2)}，已标记待人工确认（不强行判定）`,
            ok: false,
          },
        }));
      } else {
        setResult((s) => ({
          ...s,
          [pid]: {
            text: `判定 ${(r.outcome * 100).toFixed(0)}%（置信 ${(r.confidence * 100).toFixed(0)}%）`,
            ok: true,
          },
        }));
      }
      due.reload();
    } catch (e) {
      setResult((s) => ({
        ...s,
        [pid]: { text: e instanceof Error ? e.message : String(e), ok: false },
      }));
    } finally {
      setBusy(null);
    }
  };

  const items = due.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="验证"
        desc="到期的预测会主动出现在这里。成败一视同仁，系统不会只挑算准的给你看。"
        right={<Badge tone="gilt">待验证 {due.data?.count ?? 0}</Badge>}
      />

      <Card title="验证收件箱" subtitle="第 59 节：到期主动提醒，不自动判成功">
        {due.loading && <Loading />}
        {due.error && <ErrorBox message={due.error} />}
        {!due.loading && !due.error && items.length === 0 && (
          <EmptyState>当前没有到期的预测。</EmptyState>
        )}

        <ul className="stagger space-y-4">
          {items.map((it) => {
            const res = result[it.prediction_id];
            return (
              <li
                key={it.prediction_id}
                className="row-hover rounded-lg border border-line p-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="text-sm text-t1">{cleanDescription(it.description, it.event_type)}</div>
                    <div className="mt-1 text-xs text-t4">
                      {it.event_type} · 窗口 {shortDateTime(it.window[0])} ~{' '}
                      {shortDateTime(it.window[1])}
                    </div>
                  </div>
                  <Badge tone="gilt">
                    {it.probability != null ? `${(it.probability * 100).toFixed(0)}%` : '—'}
                  </Badge>
                </div>

                <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
                  <div className="rounded-lg border border-jade-500/15 bg-jade-500/5 p-2.5">
                    <div className="mb-1 font-medium text-jade-400">成功标准</div>
                    <ul className="space-y-0.5 text-t2">
                      {it.success_criteria.map((c, i) => (
                        <li key={i}>· {c}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-lg border border-cinnabar-500/15 bg-cinnabar-500/5 p-2.5">
                    <div className="mb-1 font-medium text-cinnabar-400">失败标准</div>
                    <ul className="space-y-0.5 text-t2">
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
                      className={`btn-press rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${q.cls}`}
                    >
                      {busy === it.prediction_id ? '判定中…' : q.label}
                    </button>
                  ))}
                </div>

                <div className="mt-3 flex gap-2">
                  <input
                    value={reply[it.prediction_id] ?? ''}
                    onChange={(e) =>
                      setReply((s) => ({ ...s, [it.prediction_id]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && reply[it.prediction_id] && busy !== it.prediction_id) {
                        void submit(it.prediction_id);
                      }
                    }}
                    placeholder="也可以直接描述今天发生了什么…（回车提交）"
                    className={`flex-1 ${inputCls}`}
                  />
                  <button
                    disabled={busy === it.prediction_id || !reply[it.prediction_id]}
                    onClick={() => submit(it.prediction_id)}
                    className="btn-press rounded-lg bg-t1 px-3.5 py-1.5 text-xs font-semibold text-page hover:opacity-85 disabled:opacity-40"
                  >
                    提交
                  </button>
                </div>

                {res && (
                  <div
                    className={`animate-fade-in mt-3 rounded-lg border px-3 py-2 text-xs ${
                      res.ok
                        ? 'border-jade-500/30 bg-jade-500/10 text-jade-400'
                        : 'border-amber-500/30 bg-amber-500/10 text-amber-400'
                    }`}
                  >
                    {res.text}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
