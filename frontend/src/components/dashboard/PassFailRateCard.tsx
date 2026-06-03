/* PassFailRateCard — dashboard 的「成稿率 / 废稿率」仪表盘 (R16)
 *
 * 4 个桶:
 *   - 成稿    (succeeded): status='succeeded' 或 current_score >= pass_score
 *   - 需复审  (needs_review): status='needs_review'
 *   - 失败    (failed): status='failed'
 *   - 跑批中  (in_progress): status='running' / 'queued'
 *
 * SVG 圆环 + 4 段可点击,点开侧栏列出该桶里的章节(可跳转详情).
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listChapters, getPolicy } from "../../api";
import type { Chapter, WorkerPolicy } from "../../types";
import "./PassFailRateCard.css";

type BucketKey = "succeeded" | "needs_review" | "failed" | "in_progress";

const BUCKET_META: Record<BucketKey, { label: string; color: string; short: string }> = {
  succeeded:   { label: "成稿",   color: "var(--state-ok, #4ade80)",   short: "成" },
  needs_review:{ label: "需复审", color: "var(--state-warn, #fbbf24)", short: "复" },
  failed:      { label: "失败",   color: "var(--state-error, #f87171)",short: "败" },
  in_progress: { label: "跑批中", color: "var(--accent-gold, #d4af37)",short: "跑" },
};

function bucketOf(ch: Chapter): BucketKey {
  if (ch.status === "succeeded") return "succeeded";
  if (ch.status === "needs_review") return "needs_review";
  if (ch.status === "failed") return "failed";
  if (ch.status === "running" || ch.status === "queued") return "in_progress";
  // Fallback: treat anything else as needs_review
  return "needs_review";
}

function effectiveSucceeded(ch: Chapter, passScore: number): boolean {
  if (ch.status === "succeeded") return true;
  if (typeof ch.current_score === "number" && ch.current_score >= passScore) return true;
  return false;
}

type Props = { projectId: number | null };

export function PassFailRateCard({ projectId }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);
  const [open, setOpen] = useState<BucketKey | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId) { setChapters([]); setPolicy(null); return; }
    setLoading(true);
    Promise.all([listChapters(projectId), getPolicy(projectId)])
      .then(([chs, pol]) => {
        setChapters(chs);
        setPolicy(pol);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  const passScore = policy?.pass_score ?? 80;

  // Bucket chapters using the same effective rule.
  const buckets = useMemo(() => {
    const b: Record<BucketKey, Chapter[]> = {
      succeeded: [], needs_review: [], failed: [], in_progress: [],
    };
    for (const ch of chapters) {
      if (effectiveSucceeded(ch, passScore) && ch.status !== "failed" && ch.status !== "running" && ch.status !== "queued") {
        b.succeeded.push(ch);
      } else {
        b[bucketOf(ch)].push(ch);
      }
    }
    return b;
  }, [chapters, passScore]);

  const total = chapters.length;
  // Denominator excludes in_progress (we can't say "failed" or
  // "succeeded" about something still running).
  const decided = buckets.succeeded.length + buckets.needs_review.length + buckets.failed.length;
  const passRate = decided > 0 ? Math.round((buckets.succeeded.length / decided) * 100) : 0;
  const failRate = decided > 0 ? Math.round((buckets.failed.length / decided) * 100) : 0;
  const reviewRate = decided > 0 ? Math.round((buckets.needs_review.length / decided) * 100) : 0;

  if (!projectId) {
    return (
      <section className="card pfr-card">
        <div className="card-header">
          <h3>成稿率 / 废稿率</h3>
        </div>
        <div className="muted small" style={{ padding: 16 }}>选一个项目后,这里会显示该项目的章节成 / 败 / 待复审分布。</div>
      </section>
    );
  }

  if (loading && total === 0) {
    return (
      <section className="card pfr-card">
        <div className="card-header">
          <h3>成稿率 / 废稿率</h3>
        </div>
        <div className="muted small" style={{ padding: 16 }}>加载中…</div>
      </section>
    );
  }

  return (
    <section className="card pfr-card">
      <div className="card-header">
        <h3>成稿率 / 废稿率</h3>
        <span className="muted small">项目 #{projectId} · 共 {total} 章 · 已判定 {decided}</span>
      </div>

      {total === 0 ? (
        <div className="muted small" style={{ padding: 16 }}>该项目中还没有章节。</div>
      ) : (
        <div className="pfr-body">
          <Donut buckets={buckets} passRate={passRate} failRate={failRate} decided={decided} onClick={setOpen} />
          <div className="pfr-legend">
            {(Object.keys(buckets) as BucketKey[]).map((k) => {
              const meta = BUCKET_META[k];
              const n = buckets[k].length;
              const pct = decided > 0 ? Math.round((n / decided) * 100) : 0;
              const active = open === k;
              return (
                <button
                  key={k}
                  className={`pfr-legend-item ${active ? "active" : ""}`}
                  onClick={() => setOpen(active ? null : k)}
                  title={`点击查看「${meta.label}」的章节 (${n} 条)`}
                >
                  <span className="pfr-legend-dot" style={{ background: meta.color }} />
                  <span className="pfr-legend-label">{meta.label}</span>
                  <span className="pfr-legend-num">{n}</span>
                  <span className="pfr-legend-pct">{pct}%</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {open && (
        <ChapterListDrawer
          bucket={open}
          chapters={buckets[open]}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}

function Donut({
  buckets, passRate, failRate, decided, onClick,
}: {
  buckets: Record<BucketKey, Chapter[]>;
  passRate: number;
  failRate: number;
  decided: number;
  onClick: (k: BucketKey) => void;
}) {
  // SVG donut. 4 segments with stroke-dasharray math.
  const r = 60;
  const cx = 80, cy = 80;
  const C = 2 * Math.PI * r;
  // We render segments in fixed order, each with offset.
  const order: BucketKey[] = ["succeeded", "needs_review", "failed", "in_progress"];
  const total = order.reduce((s, k) => s + buckets[k].length, 0);
  if (total === 0) {
    return <div className="pfr-donut-empty muted">—</div>;
  }
  let acc = 0;
  return (
    <div className="pfr-donut-wrap">
      <svg width={160} height={160} className="pfr-donut" viewBox="0 0 160 160">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--bg-elev)" strokeWidth={20} />
        {order.map((k) => {
          const n = buckets[k].length;
          if (n === 0) return null;
          const seg = C * (n / total);
          const offset = C * (acc / total);
          acc += n;
          const meta = BUCKET_META[k];
          return (
            <circle
              key={k}
              cx={cx} cy={cy} r={r}
              fill="none"
              stroke={meta.color}
              strokeWidth={20}
              strokeDasharray={`${seg} ${C - seg}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${cx} ${cy})`}
              className="pfr-donut-seg"
              onClick={() => onClick(k)}
              style={{ cursor: "pointer" }}
            >
              <title>{meta.label} · {n} 章</title>
            </circle>
          );
        })}
        <text x={cx} y={cy - 4} textAnchor="middle" className="pfr-donut-num">{passRate}%</text>
        <text x={cx} y={cy + 14} textAnchor="middle" className="pfr-donut-sub">成稿率</text>
      </svg>
      <div className="pfr-rate-row">
        <span className="pfr-rate">
          <span className="pfr-rate-num" style={{ color: BUCKET_META.failed.color }}>{failRate}%</span>
          <span className="pfr-rate-label">废稿率</span>
        </span>
        <span className="pfr-rate">
          <span className="pfr-rate-num" style={{ color: BUCKET_META.needs_review.color }}>{buckets.needs_review.length + buckets.failed.length > 0 ? Math.round(((buckets.needs_review.length + buckets.failed.length) / Math.max(decided, 1)) * 100) : 0}%</span>
          <span className="pfr-rate-label">需复审+失败</span>
        </span>
      </div>
    </div>
  );
}

function ChapterListDrawer({
  bucket, chapters, onClose,
}: {
  bucket: BucketKey;
  chapters: Chapter[];
  onClose: () => void;
}) {
  const meta = BUCKET_META[bucket];
  return (
    <div className="pfr-drawer" onClick={onClose}>
      <div className="pfr-drawer-inner" onClick={(e) => e.stopPropagation()}>
        <div className="pfr-drawer-head">
          <h4>
            <span className="pfr-legend-dot" style={{ background: meta.color }} />
            {meta.label} · {chapters.length} 章
          </h4>
          <button onClick={onClose} aria-label="关闭">✕</button>
        </div>
        {chapters.length === 0 ? (
          <div className="muted small" style={{ padding: 16 }}>这一类没有章节。</div>
        ) : (
          <table className="pfr-drawer-table">
            <thead>
              <tr>
                <th>#</th>
                <th>标题</th>
                <th>状态</th>
                <th>分数</th>
                <th>字数</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {chapters.map((ch) => (
                <tr key={ch.id}>
                  <td className="mono muted">{ch.chapter_no}</td>
                  <td>
                    <Link to={`/projects/${ch.project_id}/chapters/${ch.id}`} onClick={onClose}>
                      {ch.title}
                    </Link>
                  </td>
                  <td>
                    <span className={`pill ${ch.status}`}>{ch.status}</span>
                  </td>
                  <td className="mono">{ch.current_score ?? "—"}</td>
                  <td className="mono">{(ch.actual_word_count ?? 0).toLocaleString()}</td>
                  <td className="muted tiny">{ch.updated_at ? new Date(ch.updated_at).toLocaleString("zh-CN") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
