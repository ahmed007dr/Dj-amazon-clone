import type { CouponPeriod } from '@/features/pricing/api';

/**
 * The period the coupon screen reads its figures for.
 *
 * ⚠️  One state object feeds the stat cards, the table's "times used / net sales"
 *     columns, the insights drawer and the Excel export — so they can never describe
 *     different periods. The server filters; this only builds the two query params.
 */
export type PeriodPreset = 'all' | 'month' | 'last30' | 'custom';

export interface PeriodState {
  preset: PeriodPreset;
  /** `YYYY-MM-DD`, only read when `preset === 'custom'`. */
  from: string;
  to: string;
}

export const ALL_TIME: PeriodState = { preset: 'all', from: '', to: '' };

/** A local calendar day as `YYYY-MM-DD` — not `toISOString()`, which shifts it into UTC. */
function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${String(date.getFullYear())}-${month}-${day}`;
}

/**
 * ⚠️  An inverted custom range is reported rather than sent: the server refuses it
 *     (zeros that look genuine are worse than an error), and a screen that waits for
 *     the 400 shows an error toast for something the form could have said while typing.
 */
export function isInvertedRange(period: PeriodState): boolean {
  return period.preset === 'custom' && Boolean(period.from && period.to && period.from > period.to);
}

export function periodParams(period: PeriodState, now: Date = new Date()): CouponPeriod {
  switch (period.preset) {
    case 'month':
      return { date_from: isoDay(new Date(now.getFullYear(), now.getMonth(), 1)) };
    case 'last30': {
      const start = new Date(now);
      start.setDate(start.getDate() - 29);
      return { date_from: isoDay(start) };
    }
    case 'custom':
      if (isInvertedRange(period)) return {};
      return {
        ...(period.from ? { date_from: period.from } : {}),
        ...(period.to ? { date_to: period.to } : {}),
      };
    default:
      return {};
  }
}
