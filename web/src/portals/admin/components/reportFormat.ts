/**
 * A percentage the server computed (0..100) → "42.5%".
 *
 * ⚠️  Displayed, never recomputed: the table, the cards and the export all read the server's
 *     own rate, so they cannot disagree by a rounding rule applied in one place only.
 *     A missing value is a dash, not "0%" — "no data" and "none converted" are different.
 */
export function formatRate(raw: number | string | null | undefined, locale: string): string {
  if (raw === null || raw === undefined || raw === '') return '—';
  const value = typeof raw === 'number' ? raw : Number.parseFloat(raw);
  if (Number.isNaN(value)) return '—';
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)}%`;
}
