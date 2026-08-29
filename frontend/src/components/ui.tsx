import type { ReactNode } from 'react';

export function Card({
  title,
  subtitle,
  right,
  children,
  className = '',
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-ink-700 bg-ink-900 p-4 ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-200">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: 'default' | 'good' | 'bad' | 'warn';
}) {
  const toneClass = {
    default: 'text-slate-100',
    good: 'text-jade-400',
    bad: 'text-cinnabar-400',
    warn: 'text-amber-400',
  }[tone];
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 px-4 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular ${toneClass}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-600">{hint}</div>}
    </div>
  );
}

export function Badge({
  children,
  tone = 'default',
}: {
  children: ReactNode;
  tone?: 'default' | 'good' | 'bad' | 'warn' | 'info';
}) {
  const cls = {
    default: 'bg-ink-700 text-slate-300',
    good: 'bg-jade-600/20 text-jade-400',
    bad: 'bg-cinnabar-500/20 text-cinnabar-400',
    warn: 'bg-amber-500/20 text-amber-400',
    info: 'bg-sky-500/20 text-sky-400',
  }[tone];
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {children}
    </span>
  );
}

export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-slate-500">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
      {label}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded border border-cinnabar-500/40 bg-cinnabar-500/10 px-3 py-2 text-sm text-cinnabar-400">
      {message}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-ink-700 px-4 py-8 text-center text-sm text-slate-600">
      {children}
    </div>
  );
}

/** 概率条（方案第 29.1 节首页） */
export function ProbBar({ p, className = '' }: { p: number; className?: string }) {
  const color =
    p >= 0.7 ? 'bg-jade-500' : p >= 0.5 ? 'bg-amber-500' : 'bg-sky-500';
  return (
    <div className={`prob-bar ${className}`}>
      <div className={color} style={{ width: `${Math.round(p * 100)}%` }} />
    </div>
  );
}
