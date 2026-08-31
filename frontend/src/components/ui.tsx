import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react';

import { useCountUp } from '../lib/useCountUp';

/* ------------------------------------------------------------------ */
/* 布局                                                                */
/* ------------------------------------------------------------------ */

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
    <section
      className={`card-hover relative rounded-2xl border border-bd bg-card p-5 shadow-card ${className}`}
    >
      {(title || right) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold tracking-tight text-t1">{title}</h2>
            )}
            {subtitle && (
              <p className="mt-1 text-xs leading-relaxed text-t3">{subtitle}</p>
            )}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

/** 页面头部：大标题（tracking-tight）+ 副标题 + 右侧操作区 */
export function PageHeader({
  title,
  desc,
  right,
}: {
  title: string;
  desc: string;
  right?: ReactNode;
}) {
  return (
    <header className="flex items-end justify-between gap-4 pb-1">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-t1">{title}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-t3">{desc}</p>
      </div>
      {right && <div className="flex shrink-0 items-center gap-3">{right}</div>}
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* 数据展示                                                            */
/* ------------------------------------------------------------------ */

function AnimatedValue({ value, tone }: { value: ReactNode; tone: string }) {
  // 数值型走 count-up；文本型（'—' 等）直接渲染
  const numeric =
    typeof value === 'number' ? value : typeof value === 'string' && value !== '' && !Number.isNaN(Number(value)) ? Number(value) : null;
  const animated = useCountUp(numeric);
  if (numeric !== null && animated !== null) {
    const isInt = Number.isInteger(numeric);
    return (
      <div className={`mt-1.5 text-3xl font-semibold tracking-tight tabular ${tone}`}>
        {isInt ? Math.round(animated) : animated.toFixed(3)}
      </div>
    );
  }
  return (
    <div className={`mt-1.5 text-3xl font-semibold tracking-tight tabular ${tone}`}>{value}</div>
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
    default: 'text-t1',
    good: 'text-jade-400',
    bad: 'text-cinnabar-400',
    warn: 'text-amber-400',
  }[tone];
  const barClass = {
    default: 'bg-slate-600',
    good: 'bg-jade-500',
    bad: 'bg-cinnabar-500',
    warn: 'bg-amber-500',
  }[tone];
  return (
    <div className="card-hover relative overflow-hidden rounded-2xl border border-bd bg-card px-5 py-4 shadow-card">
      <div className={`absolute inset-x-0 top-0 h-0.5 ${barClass} opacity-60`} />
      <div className="text-[11px] font-medium uppercase tracking-wider text-t3">
        {label}
      </div>
      <AnimatedValue value={value} tone={toneClass} />
      {hint && <div className="mt-0.5 text-xs text-t4">{hint}</div>}
    </div>
  );
}

export function Badge({
  children,
  tone = 'default',
}: {
  children: ReactNode;
  tone?: 'default' | 'good' | 'bad' | 'warn' | 'info' | 'gilt';
}) {
  const cls = {
    default: 'border-bd bg-white/[0.04] text-t1',
    good: 'border-jade-500/25 bg-jade-500/10 text-jade-400',
    bad: 'border-cinnabar-500/25 bg-cinnabar-500/10 text-cinnabar-400',
    warn: 'border-amber-500/25 bg-amber-500/10 text-amber-400',
    info: 'border-sky-500/25 bg-sky-500/10 text-sky-400',
    gilt: 'border-gilt-500/25 bg-gilt-500/10 text-gt',
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${cls}`}
    >
      {children}
    </span>
  );
}

/** 概率条（方案第 29.1 节：一眼看出高低） */
export function ProbBar({ p, className = '' }: { p: number; className?: string }) {
  const color =
    p >= 0.7
      ? 'bg-jade-500 text-jade-500'
      : p >= 0.5
        ? 'bg-amber-500 text-amber-500'
        : 'bg-sky-500 text-sky-500';
  return (
    <div className={`prob-bar ${className}`}>
      <div className={color} style={{ width: `${Math.round(p * 100)}%` }} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 状态                                                                */
/* ------------------------------------------------------------------ */

export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="animate-fade-in space-y-2.5 py-1" role="status" aria-label={label}>
      <div className="skeleton h-3.5 w-2/5" />
      <div className="skeleton h-3.5 w-4/5" />
      <div className="skeleton h-3.5 w-3/5" />
      <div className="pt-1 text-xs text-t4">{label}</div>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="animate-fade-in rounded-xl border border-cinnabar-500/30 bg-cinnabar-500/[0.08] px-4 py-3 text-sm leading-relaxed text-cinnabar-400">
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-in flex flex-col items-center rounded-xl border border-dashed border-bd px-4 py-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-gilt-500/25 bg-gilt-500/[0.08] text-gt">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          className="h-5 w-5"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 3" />
        </svg>
      </div>
      {title && <div className="text-sm font-medium text-t1">{title}</div>}
      {children && (
        <div className="mt-1.5 max-w-md text-xs leading-relaxed text-t4">{children}</div>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 按钮                                                                */
/* ------------------------------------------------------------------ */

/** 主按钮：实心鎏金，active 按压反馈 */
export function PrimaryButton({
  children,
  busy = false,
  className = '',
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={`btn-press inline-flex items-center gap-2 rounded-xl bg-gilt-500 px-4 py-2 text-sm font-semibold text-[#0b0e14] hover:bg-gilt-400 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    >
      {busy && (
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#0b0e14]/30 border-t-[#0b0e14]" />
      )}
      {children}
    </button>
  );
}

/** 次级按钮 */
export function GhostButton({
  children,
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`btn-press rounded-xl border border-bd px-3 py-1.5 text-xs font-medium text-t1 hover:border-line hover:text-t1 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* 表单（label 在上，error 在下，gap-2）                                */
/* ------------------------------------------------------------------ */

export const inputCls =
  'input-glow rounded-xl border border-bd bg-panel px-3 py-2 text-sm text-t1 placeholder:text-t4';

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-xs font-medium text-t2">{label}</label>
      {children}
      {error ? (
        <div className="text-xs text-cinnabar-400">{error}</div>
      ) : hint ? (
        <div className="text-[11px] text-t4">{hint}</div>
      ) : null}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} w-full ${props.className ?? ''}`} />;
}
