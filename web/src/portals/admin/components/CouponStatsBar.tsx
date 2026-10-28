import { useTranslation } from 'react-i18next';

import { useCouponOverview, type CouponPeriod } from '@/features/pricing/api';
import { Alert } from '@/shared/ui/Alert';
import { StatCard } from '@/shared/ui/StatCard';
import { formatMoney, formatNumber } from '@/shared/utils/format';

import {
  isInvertedRange,
  type PeriodPreset,
  type PeriodState,
} from '@/portals/admin/components/couponPeriod';

import './CouponInsights.css';

const PRESETS: PeriodPreset[] = ['all', 'month', 'last30', 'custom'];

const PRESET_KEY: Record<PeriodPreset, string> = {
  all: 'pricing.insights.periodAll',
  month: 'pricing.insights.periodMonth',
  last30: 'pricing.insights.periodLast30',
  custom: 'pricing.insights.periodCustom',
};

/**
 * The period selector: this month · last 30 days · all time · custom.
 *
 * ⚠️  Native date inputs, bound to labels: they bring a picker on every platform,
 *     work in RTL and read back in the browser's own locale — a hand-built calendar
 *     would need all three done again.
 */
export function CouponPeriodFilter({
  value,
  onChange,
}: {
  value: PeriodState;
  onChange: (next: PeriodState) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="coupon-period">
      <label className="coupon-period__field">
        <span>{t('pricing.insights.period')}</span>
        <select
          value={value.preset}
          onChange={(event) => {
            onChange({ ...value, preset: event.target.value as PeriodPreset });
          }}
        >
          {PRESETS.map((preset) => (
            <option key={preset} value={preset}>
              {t(PRESET_KEY[preset])}
            </option>
          ))}
        </select>
      </label>

      {value.preset === 'custom' ? (
        <>
          <label className="coupon-period__field">
            <span>{t('pricing.insights.from')}</span>
            <input
              type="date"
              value={value.from}
              max={value.to || undefined}
              onChange={(event) => {
                onChange({ ...value, from: event.target.value });
              }}
            />
          </label>
          <label className="coupon-period__field">
            <span>{t('pricing.insights.to')}</span>
            <input
              type="date"
              value={value.to}
              min={value.from || undefined}
              onChange={(event) => {
                onChange({ ...value, to: event.target.value });
              }}
            />
          </label>
        </>
      ) : null}
    </div>
  );
}

/**
 * The stat-card row above the coupon table.
 *
 * ⚠️  One request feeds the cards **and** the ranking: the overview endpoint returns
 *     the totals across every coupon and the coupons ordered by sales, so the top-5
 *     list can never disagree with the cards above it.
 *
 * ⚠️  The help line under the cards states the definition of a sale. A number with no
 *     definition is how "we sold 40k through the code" turns into an argument about
 *     whether cancelled orders were in it.
 */
export function CouponStatsBar({
  period,
  params,
  onOpen,
}: {
  period: PeriodState;
  params: CouponPeriod;
  onOpen: (target: { id: string; code: string }) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const invalid = isInvertedRange(period);
  const overview = useCouponOverview({ ...params, ordering: '-net_sales', limit: 5 }, !invalid);

  if (invalid) return <Alert tone="warning">{t('pricing.insights.invertedRange')}</Alert>;
  if (overview.error) return <Alert tone="danger">{t('pricing.insights.loadError')}</Alert>;

  const totals = overview.data?.totals;
  const counts = overview.data?.counts;
  const ranked = (overview.data?.results ?? []).filter((row) => row.orders > 0);

  const excluded = totals ? totals.cancelled_orders + totals.refunded_orders + totals.failed_orders : 0;

  return (
    <section className="coupon-stats" aria-label={t('pricing.insights.title')}>
      <div className="coupon-stats__cards">
        <StatCard
          label={t('pricing.insights.statCoupons')}
          value={counts ? formatNumber(counts.coupons, locale) : '—'}
          hint={
            counts
              ? t('pricing.insights.statCouponsHint', {
                  running: counts.running,
                  expired: counts.expired,
                  holders: counts.with_holder,
                })
              : ''
          }
          icon="◈"
        />
        <StatCard
          label={t('pricing.insights.statUses')}
          value={totals ? formatNumber(totals.times_used, locale) : '—'}
          hint={
            totals ? t('pricing.insights.statUsesHint', { customers: totals.customers }) : ''
          }
          icon="↻"
        />
        <StatCard
          label={t('pricing.insights.statDiscount')}
          value={totals ? formatMoney(totals.discount_given, locale) : '—'}
          hint={
            totals
              ? t('pricing.insights.statDiscountHint', { count: totals.coupons_used })
              : ''
          }
          tone="warning"
          icon="%"
        />
        <StatCard
          label={t('pricing.insights.statSales')}
          value={totals ? formatMoney(totals.net_sales, locale) : '—'}
          hint={totals ? t('pricing.insights.statSalesHint', { count: totals.orders }) : ''}
          tone="success"
          icon="◔"
        />
      </div>

      <p className="coupon-stats__help muted">
        {t('pricing.insights.salesHelp')}
        {excluded > 0 && totals ? (
          <>
            {' '}
            <strong>{t('pricing.insights.excluded')}:</strong>{' '}
            {t('pricing.insights.excludedLine', {
              cancelled: totals.cancelled_orders,
              refunded: totals.refunded_orders,
              amount: formatMoney(totals.refunded_amount, locale),
              failed: totals.failed_orders,
            })}
          </>
        ) : null}
      </p>

      {ranked.length > 0 ? (
        <div className="coupon-stats__top">
          <h3>{t('pricing.insights.top')}</h3>
          <ol>
            {ranked.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => {
                    onOpen({ id: row.id, code: row.code });
                  }}
                >
                  <code dir="ltr">{row.code}</code>
                  <span className="coupon-stats__holder">{row.holder_name || '—'}</span>
                  <strong dir="ltr">{formatMoney(row.net_sales, locale)}</strong>
                </button>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
