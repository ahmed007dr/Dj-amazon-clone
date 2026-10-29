import { useId, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import type { CouponTypeSeries } from '@/features/pricing/api';
import { formatDate, formatMoney, formatNumber } from '@/shared/utils/format';

import './CouponInsights.css';
import './CouponReport.css';

type Metric = 'discount' | 'orders';
type Kind = 'registered' | 'guest';

/**
 * Discount volume (or orders) per day — or per month for a long range — as **paired bars**,
 * one for registered buyers and one for guests.
 *
 * ⚠️  Paired, not stacked: the owner's question is "how much do guests take compared with
 *     members?", which is a comparison of two heights side by side. Stacking hides the
 *     lower series' trend behind the upper one.
 *
 * ⚠️  Dependency-free, like `CouponDailyChart`, and accessible without the picture: the
 *     bars are decoration over a data table (`<details>`), the focused day is read out in a
 *     live region, and the arrow keys walk the days.
 *
 * ⚠️  Two series ⇒ a legend, always — and the guest series is **hatched**, so identity is
 *     never carried by colour alone. One axis, zero-based: a quiet day is a stub, not a gap.
 *
 * ⚠️  Money arrives as strings (ADR-31): parsed only to size a bar; what is printed is the
 *     server's own string through `formatMoney`.
 */
export function CouponTypeChart({ series }: { series: CouponTypeSeries | undefined }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const tableId = useId();

  const [metric, setMetric] = useState<Metric>('discount');
  const [active, setActive] = useState<number | null>(null);

  const points = series?.points ?? [];
  const granularity = series?.granularity ?? 'day';

  const valueOf = (index: number, kind: Kind): number => {
    const point = points[index];
    if (!point) return 0;
    return metric === 'orders' ? point[kind].orders : Number.parseFloat(point[kind].discount) || 0;
  };

  const text = (index: number, kind: Kind): string => {
    const point = points[index];
    if (!point) return '';
    return metric === 'orders'
      ? formatNumber(point[kind].orders, locale)
      : formatMoney(point[kind].discount, locale);
  };

  const max = Math.max(
    0,
    ...points.flatMap((_, index) => [valueOf(index, 'registered'), valueOf(index, 'guest')]),
  );

  const label = (date: string): string =>
    granularity === 'month'
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
    return (
      <section className="report-chart surface">
        <h3>{t('pricing.report.chartTitle')}</h3>
        <p className="report-note">{t('pricing.report.chartEmpty')}</p>
      </section>
    );
  }

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <section className="report-chart surface">
      <div className="report-chart__head">
        <h3>
          {t('pricing.report.chartTitle')} ·{' '}
          <small className="muted">
            {granularity === 'month'
              ? t('pricing.insights.chartMonth')
              : t('pricing.insights.chartDay')}
          </small>
        </h3>

        <div className="coupon-chart__metrics" role="group" aria-label={t('pricing.report.chartTitle')}>
          {(['discount', 'orders'] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={metric === item}
              onClick={() => {
                setMetric(item);
              }}
            >
              {t(item === 'discount' ? 'pricing.report.metricDiscount' : 'pricing.report.metricOrders')}
            </button>
          ))}
        </div>
      </div>

      <ul className="report-chart__legend">
        {(['registered', 'guest'] as const).map((kind) => (
          <li key={kind}>
            <span className={`report-split__swatch is-${kind}`} aria-hidden />
            {t(kind === 'registered' ? 'pricing.report.registered' : 'pricing.report.guest')}
          </li>
        ))}
      </ul>

      <div
        className="report-chart__plot"
        dir="ltr"
        role="group"
        tabIndex={0}
        aria-label={t('pricing.report.chartTitle')}
        aria-describedby={tableId}
        onKeyDown={onKey}
        onBlur={() => {
          setActive(null);
        }}
        onMouseLeave={() => {
          setActive(null);
        }}
      >
        {points.map((point, index) => (
          <div
            key={point.date}
            className={`report-chart__group ${active === index ? 'is-active' : ''}`}
            onMouseEnter={() => {
              setActive(index);
            }}
            onClick={() => {
              setActive(index);
            }}
          >
            {(['registered', 'guest'] as const).map((kind) => {
              const value = valueOf(index, kind);
              const height = max > 0 ? (value / max) * 100 : 0;
              return (
                <span
                  key={kind}
                  className={`report-chart__bar is-${kind} ${value === 0 ? 'is-empty' : ''}`}
                  style={{ blockSize: value === 0 ? '2px' : `max(${String(height)}%, 3px)` }}
                />
              );
            })}
          </div>
        ))}
      </div>

      <div className="coupon-chart__axis" dir="ltr" aria-hidden>
        <span>{first ? label(first.date) : ''}</span>
        <span>{last && last !== first ? label(last.date) : ''}</span>
      </div>

      <p className="coupon-chart__readout" aria-live="polite">
        {active !== null && points[active]
          ? `${label(points[active].date)} · ${t('pricing.report.registered')}: ${text(
              active,
              'registered',
            )} · ${t('pricing.report.guest')}: ${text(active, 'guest')}`
          : ''}
      </p>

      <details className="coupon-chart__table" id={tableId}>
        <summary>{t('pricing.insights.showTable')}</summary>
        <div className="coupon-chart__table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('pricing.insights.colDate')}</th>
                <th scope="col">
                  {t('pricing.report.registered')} · {t('pricing.report.metricDiscount')}
                </th>
                <th scope="col">
                  {t('pricing.report.guest')} · {t('pricing.report.metricDiscount')}
                </th>
                <th scope="col">
                  {t('pricing.report.registered')} · {t('pricing.report.metricOrders')}
                </th>
                <th scope="col">
                  {t('pricing.report.guest')} · {t('pricing.report.metricOrders')}
                </th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.date}>
                  <th scope="row">{label(point.date)}</th>
                  <td>{formatMoney(point.registered.discount, locale)}</td>
                  <td>{formatMoney(point.guest.discount, locale)}</td>
                  <td>{formatNumber(point.registered.orders, locale)}</td>
                  <td>{formatNumber(point.guest.orders, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
