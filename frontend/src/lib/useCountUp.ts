import { useEffect, useRef, useState } from 'react';

/**
 * 数字滚动动画：值变化时从旧值平滑过渡到新值。
 * 非数字输入（null / '—'）直接透传。
 */
export function useCountUp(target: number | null | undefined, duration = 700): number | null {
  const [display, setDisplay] = useState<number | null>(target ?? null);
  const prevRef = useRef<number>(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (target == null || Number.isNaN(target)) {
      setDisplay(null);
      return;
    }
    const from = prevRef.current;
    const to = target;
    if (from === to) {
      setDisplay(to);
      return;
    }
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      prevRef.current = to;
      setDisplay(to);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutExpo
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
      const value = from + (to - from) * eased;
      setDisplay(value);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        prevRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return display;
}
