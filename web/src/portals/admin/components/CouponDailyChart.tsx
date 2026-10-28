import { useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import type { CouponInsights } from '@/features/pricing/api';
import { formatDate, formatMoney, formatNumber } from '@/shared/utils/format';

import './CouponInsights.css';

type Metric = 'uses' | 'sales';

/**
 * Uses and net sales per day (per month for a long range) as plain bars.
 *
 * ⚠️  **Dependency-free on purpose** — a handful of flex bars, no chart library for a
 *     figure this small. And accessible without the picture: the bars are decoration
 *     over a data table (`<details>`), the focused bar is read out in a live region,
 *     and the arrow keys walk the days — 90 tab stops would be 90 presses to get past it.
 *
 * ⚠️  One series, so no legend; the toggle names it. The baseline is kept even for an
 *     empty day (a faint stub) so a quiet week reads as "nothing happened" rather
 *     than "the chart is missing a bar".
 *
 * ⚠️  Money arrives as strings (ADR-31) and is parsed only to size a bar — the number
 *     printed is the server's own string through `formatMoney`.
 */
export function CouponDailyChart({ series }: { series: CouponInsights['series'] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const [metric, setMetric] = useState<Metric>('sales');
  const [active, setActive] = useState<number | null>(null);

  const points = series.points;
  const valueOf = (index: number): number => {
    const point = points[index];
    if (!point) return 0;
    return metric === 'uses' ? point.redemptions : Number.parseFloat(point.net_sales) || 0;
  };

  const max = Math.max(0, ...points.map((_, index) => valueOf(index)));
  const format = (index: number): string => {
    const point = points[index];
    if (!point) return '';
    return metric === 'uses'
      ? formatNumber(point.redemptions, locale)
      : formatMoney(point.net_sales, locale);
  };

  const label = (date: string): string =>
    series.granularity === 'month'
      ? new Intl.DateTimeFormat(locale, { month: 'short', year: 'numeric' }).format(
          new Date(`${date}T00:00:00`),
        )
      : formatDate(`${date}T00:00:00`, locale);

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const last = points.length - 1;
    // The plot is forced left-to-right, so Right is always "later"
    if (event.key === 'ArrowRight') setActive((current) => Math.min((current ?? -1) + 1, last));
    else if (event.key === 'ArrowLeft') setActive((current) => Math.max((current ?? 1) - 1, 0));
    else if (event.key === 'Home') setActive(0);
    else if (event.key === 'End') setActive(last);
    else return;
    event.preventDefault();
  };

  if (points.length === 0) {
    return <p className="coupon-insights__note">{t('pricing.insights.chartEmpty')}</p>;
  }

  const current = active !== null ? points[active] : undefined;
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className="coupon-chart">
      <div className="coupon-chart__head">
        <h3>
          {t('pricing.insights.chartTitle')} ·{' '}
          <small className="muted">
            {series.granularity === 'month'
              ? t('pricing.insights.chartMonth')
              : t('pricing.insights.chartDay')}
          </small>
        </h3>

        <div className="coupon-chart__metrics" role="group" aria-label={t('pricing.insights.chartTitle')}>
          {(['sales', 'uses'] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={metric === item}
              onClick={() => {
                setMetric(item);
              }}
            >
              {item === 'uses'
                ? t('pricing.insights.metricUses')
                : t('pricing.insights.metricSales')}
            </button>
          ))}
        </div>
      </div>

      <div
        className="coupon-chart__plot"
        dir="ltr"
        role="group"
        tabIndex={0}
        aria-label={`${t('pricing.insights.chartTitle')} — ${t('pricing.insights.showTable')}`}
        onKeyDown={onKey}
        onBlur={() => {
          setActive(null);
        }}
        onMouseLeave={() => {
          setActive(null);
        }}
      >
        {points.map((point, index) => {
          const value = valueOf(index);
          const height = max > 0 ? (value / max) * 100 : 0;
          return (
            <div
              key={point.date}
              className={`coupon-chart__bar ${value === 0 ? 'is-empty' : ''} ${
                active === index ? 'is-active' : ''
              }`}
              // A zero day keeps a 2px stub so the baseline reads as data, not as a gap
              style={{ blockSize: value === 0 ? '2px' : `max(${String(height)}%, 3px)` }}
              onMouseEnter={() => {
                setActive(index);
              }}
              onClick={() => {
                setActive(index);
              }}
            />
          );
        })}
      </div>

      <div className="coupon-chart__axis" dir="ltr" aria-hidden>
        <span>{first ? label(first.date) : ''}</span>
        <span>{last && last !== first ? label(last.date) : ''}</span>
      </div>

      <p className="coupon-chart__readout" aria-live="polite">
        {current && active !== null
          ? `${label(current.date)} · ${format(active)}`
          : max > 0
            ? `${t('pricing.insights.net')}: ${formatMoney(
                points.reduce((sum, point) => sum + (Number.parseFloat(point.net_sales) || 0), 0),
                locale,
              )}`
            : ''}
      </p>

      <details className="coupon-chart__table">
        <summary>{t('pricing.insights.showTable')}</summary>
        <div className="coupon-chart__table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('pricing.insights.colDate')}</th>
                <th scope="col">{t('pricing.insights.metricUses')}</th>
                <th scope="col">{t('pricing.insights.orders')}</th>
                <th scope="col">{t('pricing.insights.metricSales')}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.date}>
                  <th scope="row">{label(point.date)}</th>
                  <td>{formatNumber(point.redemptions, locale)}</td>
                  <td>{formatNumber(point.orders, locale)}</td>
                  <td>{formatMoney(point.net_sales, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
