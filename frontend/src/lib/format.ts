/**
 * Small formatters reused across the UI.
 *
 * formatThousands: 12345 -> "12,345"; >= 10000 -> "1.2万"
 * (Chinese publishing convention).
 */
export function formatThousands(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
