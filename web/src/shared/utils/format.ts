/**
 * Formatting — numbers, currency and dates.
 *
 * ⚠️  Always `Intl`, never manual formatting.
 *
 *     The decimal separator, the thousands separator and the position of the
 *     currency symbol all differ between Arabic and English — the Arabic-locale
 *     rendering against `EGP 1,234.50`. Manual formatting produces one of them
 *     in both languages.
 *
 * ⚠️  Money arrives from the server **as a string**, not a number (ADR-31).
 *
 *     Converting it to a `number` in JavaScript loses precision at large
 *     amounts, and display here is the only permitted use. Any financial
 *     arithmetic happens on the server.
 */

const CURRENCY = 'EGP';

export function formatMoney(value: string | number, locale: string): string {
  const amount = typeof value === 'string' ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return '—';

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: CURRENCY,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}

export function formatDate(value: string | Date, locale: string): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
  }).format(date);
}

export function formatDateTime(value: string | Date, locale: string): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

/** "3 days ago" — in the correct locale and with no library. */
export function formatRelative(value: string | Date, locale: string): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  const seconds = (date.getTime() - Date.now()) / 1000;

  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31_536_000],
    ['month', 2_592_000],
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ];

  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return formatter.format(Math.round(seconds / size), unit);
    }
  }
  return formatter.format(Math.round(seconds), 'second');
}
