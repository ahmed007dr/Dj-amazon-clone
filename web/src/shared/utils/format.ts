/**
 * التنسيق — أرقام وعملة وتواريخ.
 *
 * ⚠️  `Intl` دائمًا، ولا تنسيق يدوي.
 *
 *     الفاصلة العشرية والألفية وموضع رمز العملة كلها تختلف بين
 *     العربية والإنجليزية. «١٢٣٤٫٥٠ ج.م» مقابل «EGP 1,234.50» —
 *     والتنسيق اليدوي ينتج أحدهما في اللغتين.
 *
 * ⚠️  المال يصل من الخادم **نصًّا** لا رقمًا (ADR-31).
 *
 *     تحويله إلى `number` في JavaScript يفقد الدقة عند مبالغ
 *     كبيرة، والعرض هنا هو الاستخدام الوحيد المسموح به. أي حساب
 *     مالي يقع في الخادم.
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

/** «منذ ٣ أيام» — بالـ locale الصحيح وبلا مكتبة. */
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
