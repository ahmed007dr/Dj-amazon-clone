import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCouponInsights,
  useCouponOrders,
  type CouponOrderRow,
  type CouponPeriod,
  type CouponProductRow,
} from '@/features/pricing/api';
import { CouponDailyChart } from '@/portals/admin/components/CouponDailyChart';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate, formatDateTime, formatMoney, formatNumber } from '@/shared/utils/format';

import './CouponInsights.css';

export interface InsightsTarget {
  id: string;
  code: string;
}

/**
 * What one coupon brought in: the summary, the products it sold, a daily chart and
 * the orders behind it.
 *
 * ⚠️  **Two requests, not one**: the summary/products/series arrive together and the
 *     orders paginate on their own — a drawer that opens should not wait on a list
 *     the reader has not scrolled to.
 *
 * ⚠️  The orders list is the audit trail for every number above it: each row says
 *     whether it was **counted**. A reader who doubts the total can add the rows up.
 *
 * ⚠️  `usage_count` in the old log counts uses; this drawer counts *sales*. The gap
 *     between them (cancelled · refunded · payment failed) is shown, not hidden.
 */
export function CouponInsightsDrawer({
  target,
  period,
  onClose,
}: {
  target: InsightsTarget | null;
  period: CouponPeriod;
  onClose: () => void;
}) {
  return (
    <Drawer open={target !== null} onClose={onClose} {...(target ? { title: target.code } : {})}>
      {target ? <InsightsBody key={target.id} target={target} period={period} /> : null}
    </Drawer>
  );
}

function InsightsBody({ target, period }: { target: InsightsTarget; period: CouponPeriod }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const insights = useCouponInsights(target.id, period);

  const [only, setOnly] = useState('');
  const [page, setPage] = useState(1);
  const orders = useCouponOrders(target.id, { ...period, ...(only ? { only } : {}), page });

  if (insights.isPending) return <Spinner />;
  if (insights.error || !insights.data) {
    return <StateMessage icon="⚠" title={t('pricing.insights.loadError')} />;
  }

  const { coupon, summary, products, series } = insights.data;
  const money = (value: string) => formatMoney(value, locale);
  const unused = summary.times_used === 0 && summary.cancelled_redemptions === 0;
  const excluded = summary.cancelled_orders + summary.refunded_orders + summary.failed_orders;

  const productColumns: Column<CouponProductRow>[] = [
    {
      key: 'product',
      header: t('pricing.insights.colProduct'),
      render: (row) => (
        <span>
          <code dir="ltr">{row.sku}</code> — {locale.startsWith('ar') ? row.name_ar : row.name_en}
          {row.color_name_ar || row.color_name_en ? (
            <small className="coupon-holder">
              {row.color_hex ? (
                <span
                  className="coupon-insights__swatch"
                  style={{ background: row.color_hex }}
                  aria-hidden
                />
              ) : null}
              {locale.startsWith('ar') ? row.color_name_ar : row.color_name_en}
            </small>
          ) : null}
        </span>
      ),
    },
    {
      key: 'units',
      header: t('pricing.insights.colUnits'),
      align: 'end',
      render: (row) => formatNumber(row.units, locale),
    },
    {
      key: 'revenue',
      header: t('pricing.insights.colRevenue'),
      align: 'end',
      render: (row) => money(row.revenue),
    },
    {
      key: 'discount',
      header: t('pricing.insights.colDiscount'),
      align: 'end',
      secondary: true,
      render: (row) => money(row.discount),
    },
    {
      key: 'net',
      header: t('pricing.insights.colNet'),
      align: 'end',
      render: (row) => <strong>{money(row.net_revenue)}</strong>,
    },
  ];

  const orderColumns: Column<CouponOrderRow>[] = [
    {
      key: 'number',
      header: t('pricing.insights.orderNumber'),
      render: (row) => (
        <span className={row.counted ? '' : 'coupon-insights__muted-row'}>
          <code dir="ltr">{row.number}</code>
          <small className="coupon-holder">{formatDateTime(row.created_at, locale)}</small>
        </span>
      ),
    },
    {
      key: 'customer',
      header: t('pricing.insights.customer'),
      secondary: true,
      render: (row) => (
        <span>
          {row.customer_name || '—'}
          {row.contact ? (
            <small className="coupon-holder" dir="ltr">
              {row.contact}
            </small>
          ) : null}
        </span>
      ),
    },
    {
      key: 'amounts',
      header: t('pricing.insights.net'),
      align: 'end',
      render: (row) => (
        <span>
          <strong>{money(row.net_sales)}</strong>
          <small className="coupon-holder">
            {t('pricing.insights.discount')}: {money(row.discount)}
          </small>
        </span>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <span>
          <Badge tone={row.counted ? 'success' : 'neutral'}>
            {row.counted ? t('pricing.insights.counted') : t('pricing.insights.notCounted')}
          </Badge>
          <small className="coupon-holder">{t(`orderStatus.${row.status}`)}</small>
        </span>
      ),
    },
  ];

  return (
    <div className="coupon-insights">
      <p className="coupon-insights__who">
        <strong>{locale.startsWith('ar') ? coupon.name_ar : coupon.name_en}</strong>
        {coupon.holder_name ? (
          <small>
            {t('pricing.insights.holder')}: {coupon.holder_name}
          </small>
        ) : null}
        {coupon.holder_note ? <small>{coupon.holder_note}</small> : null}
      </p>

      {unused ? (
        <StateMessage
          icon="◈"
          title={t('pricing.insights.unusedTitle')}
          body={t('pricing.insights.unusedBody')}
        />
      ) : (
        <>
          {/* ── Summary ─────────────────────────────── */}
          <section>
            <div className="coupon-insights__cards">
              <StatCard
                label={t('pricing.insights.net')}
                value={money(summary.net_sales)}
                hint={t('pricing.insights.statSalesHint', { count: summary.orders })}
                tone="success"
              />
              <StatCard
                label={t('pricing.insights.discount')}
                value={money(summary.discount_given)}
                tone="warning"
              />
              <StatCard
                label={t('pricing.insights.gross')}
                value={money(summary.gross_sales)}
              />
              <StatCard
                label={t('pricing.insights.orderTotal')}
                value={money(summary.order_total)}
                hint={t('pricing.insights.orderTotalHint')}
              />
              <StatCard
                label={t('pricing.insights.uses')}
                value={formatNumber(summary.times_used, locale)}
              />
              <StatCard
                label={t('pricing.insights.customers')}
                value={formatNumber(summary.customers, locale)}
              />
            </div>

            <ul className="coupon-insights__facts">
              <li>
                <span>{t('pricing.insights.aov')}</span>
                <strong>{money(summary.average_order_value)}</strong>
              </li>
              <li>
                <span>{t('pricing.insights.firstUsed')}</span>
                <span>{formatDateTime(summary.first_used_at, locale)}</span>
              </li>
              <li>
                <span>{t('pricing.insights.lastUsed')}</span>
                <span>{formatDateTime(summary.last_used_at, locale)}</span>
              </li>
              <li>
                <span>{t('pricing.insights.remaining')}</span>
                <span>
                  {summary.remaining_total === null || summary.usage_limit === null
                    ? t('pricing.insights.unlimited')
                    : t('pricing.insights.remainingOf', {
                        left: summary.remaining_total,
                        total: summary.usage_limit,
                      })}
                </span>
              </li>
              <li>
                <span>{t('pricing.insights.perCustomer', { count: summary.usage_limit_per_user })}</span>
                {summary.customers_at_limit > 0 ? (
                  <span>{t('pricing.insights.atLimit', { count: summary.customers_at_limit })}</span>
                ) : null}
              </li>
              {summary.owner_remaining !== null ? (
                <li>
                  <span>{t('pricing.insights.ownerLeft', { count: summary.owner_remaining })}</span>
                  <span>{coupon.owner_email}</span>
                </li>
              ) : null}
            </ul>

            {excluded > 0 ? (
              <Alert tone="info">
                <strong>{t('pricing.insights.excluded')}:</strong>{' '}
                {t('pricing.insights.excludedLine', {
                  cancelled: summary.cancelled_orders,
                  refunded: summary.refunded_orders,
                  amount: money(summary.refunded_amount),
                  failed: summary.failed_orders,
                })}
              </Alert>
            ) : null}
          </section>

          {/* ── Chart ───────────────────────────────── */}
          <section>
            <CouponDailyChart series={series} />
          </section>

          {/* ── Products ────────────────────────────── */}
          <section>
            <h3>{t('pricing.insights.products')}</h3>
            <p className="coupon-insights__note">{t('pricing.insights.productsHelp')}</p>
            <DataTable
              columns={productColumns}
              rows={products}
              rowKey={(row) => `${row.product}:${row.variant ?? ''}`}
              emptyTitle={t('pricing.insights.noProducts')}
            />
          </section>
        </>
      )}

      {/* ── Orders ──────────────────────────────────── */}
      <section>
        <div className="coupon-insights__orders-head">
          <h3>{t('pricing.insights.recent')}</h3>
          <FilterSelect
            value={only}
            label={t('pricing.insights.filterAll')}
            options={[
              { value: 'sales', label: t('pricing.insights.filterSales') },
              { value: 'excluded', label: t('pricing.insights.filterExcluded') },
            ]}
            onChange={(next) => {
              setOnly(next);
              setPage(1);
            }}
          />
        </div>

        <DataTable
          columns={orderColumns}
          rows={orders.data?.results ?? []}
          rowKey={(row) => row.id}
          isLoading={orders.isPending}
          error={orders.error}
          emptyTitle={t('pricing.insights.noOrders')}
        />
        {orders.data ? (
          <Pagination page={orders.data.page} pages={orders.data.pages} onChange={setPage} />
        ) : null}
      </section>

      <p className="coupon-insights__note">
        {coupon.starts_at ? `${formatDate(coupon.starts_at, locale)} — ` : ''}
        {coupon.ends_at ? formatDate(coupon.ends_at, locale) : t('pricing.noEnd')}
      </p>
    </div>
  );
}
