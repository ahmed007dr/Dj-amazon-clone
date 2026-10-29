import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { downloadExport } from '@/features/exports/adminApi';
import {
  customerReport,
  useCouponHolders,
  useCouponOverview,
  type CouponGroupRow,
  type CouponPeriod,
  type CouponRankRow,
} from '@/features/pricing/api';
import { CouponCustomerSplit } from '@/portals/admin/components/CouponCustomerSplit';
import { CouponTypeChart } from '@/portals/admin/components/CouponTypeChart';
import { isInvertedRange, type PeriodState } from '@/portals/admin/components/couponPeriod';
import { formatRate } from '@/portals/admin/components/reportFormat';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatCard } from '@/shared/ui/StatCard';
import { useToast } from '@/shared/ui/useToast';
import { formatMoney, formatNumber } from '@/shared/utils/format';

import './CouponInsights.css';
import './CouponReport.css';

type GroupBy = 'coupon' | 'holder';

/** One table row, whichever way the report is grouped. `null` = the server did not say. */
interface ReportRow {
  key: string;
  holder: string;
  codes: { id: string; code: string }[];
  uses: number;
  discount: string;
  net: string;
  registered: number | null;
  guest: number | null;
  newCustomers: number | null;
}

// ⚠️  The ranking and the holder roll-up accept the same sort keys (`discount_given`,
//     `times_used`, `customers`, `new_customers` …) — one list serves both groupings.
const SORTS = [
  { value: '-net_sales', key: 'pricing.report.sortNet' },
  { value: '-discount_given', key: 'pricing.report.sortDiscount' },
  { value: '-times_used', key: 'pricing.report.sortUses' },
  { value: '-customers', key: 'pricing.report.sortCustomers' },
  { value: '-new_customers', key: 'pricing.report.sortNew' },
];

function fromCoupon(row: CouponRankRow): ReportRow {
  return {
    key: row.id,
    holder: row.holder_name,
    codes: [{ id: row.id, code: row.code }],
    uses: row.times_used,
    discount: row.discount_given,
    net: row.net_sales,
    registered: row.by_customer_type?.registered.orders ?? null,
    guest: row.by_customer_type?.guest.orders ?? null,
    newCustomers: row.new_customers?.count ?? null,
  };
}

function fromHolder(row: CouponGroupRow): ReportRow {
  return {
    // The unassigned bucket has an empty name — it still needs a stable key
    key: row.unassigned ? 'unassigned' : `holder:${row.holder_name}`,
    holder: row.holder_name,
    codes: row.codes.map((entry) => ({ id: entry.id, code: entry.code })),
    uses: row.times_used,
    discount: row.discount_given,
    net: row.net_sales,
    registered: row.registered_orders,
    guest: row.guest_orders,
    newCustomers: row.new_customers?.count ?? null,
  };
}

/**
 * The coupon report: what the discounts cost, who they went to (an account or a guest), how
 * many of those buyers were new, and which holder each code belongs to.
 *
 * ⚠️  **Registered vs guest is the way the order was placed** — a guest who opens an account
 *     afterwards is still a guest purchase. The help line says so, because the first question
 *     a reader asks of "guests: 40" is "are they really guests today?".
 *
 * ⚠️  Everything on screen is the server's figure: the cards, the split, the chart and the
 *     table come from the same period and the same endpoints as the export, so the file the
 *     owner downloads cannot disagree with what they are looking at.
 *
 * ⚠️  If the server has not sent the customer-type breakdown (an older deploy) the screen
 *     says so and still shows the totals and the table — a report that goes blank is worse
 *     than one that admits what it lacks.
 */
export function CouponReport({
  period,
  params,
  onOpen,
}: {
  period: PeriodState;
  params: CouponPeriod;
  onOpen: (target: { id: string; code: string }) => void;
}) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const locale = i18n.language;

  const invalid = isInvertedRange(period);

  const [groupBy, setGroupBy] = useState<GroupBy>('coupon');
  const [ordering, setOrdering] = useState('-net_sales');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState<'report' | 'customers' | null>(null);
  const debounced = useDebounced(search);

  // The same request the stat cards make elsewhere: one cache entry, one set of totals
  const overview = useCouponOverview({ ...params, ordering: '-net_sales', limit: 5 }, !invalid);
  const rank = useCouponOverview(
    { ...params, ...(debounced ? { search: debounced } : {}), ordering, page },
    !invalid && groupBy === 'coupon',
  );
  const holders = useCouponHolders(
    { ...params, ...(debounced ? { search: debounced } : {}), ordering, page },
    !invalid && groupBy === 'holder',
  );

  if (invalid) return <Alert tone="warning">{t('pricing.insights.invertedRange')}</Alert>;
  if (overview.error) return <Alert tone="danger">{t('pricing.insights.loadError')}</Alert>;

  const totals = overview.data?.totals;
  const report = customerReport(totals, overview.data);
  const money = (value: string | number) => formatMoney(value, locale);
  const count = (value: number) => formatNumber(value, locale);

  const table = groupBy === 'coupon' ? rank : holders;
  const rows: ReportRow[] =
    groupBy === 'coupon'
      ? (rank.data?.results ?? []).map(fromCoupon)
      : (holders.data?.results ?? []).map(fromHolder);

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  // ⚠️  The same period and search as the table, through the export system's own download flow.
  //     The `coupons` dataset is one row per coupon (holder in a column), so the file does not
  //     change with the group-by toggle; `coupon_customers` is every coupon's buyers.
  const runExport = async (kind: 'report' | 'customers') => {
    setExporting(kind);
    try {
      await downloadExport(kind === 'report' ? 'coupons' : 'coupon_customers', {
        start: params.date_from ?? '',
        end: params.date_to ?? '',
        search: debounced,
      });
      notify(t('pricing.insights.exported'), 'success');
    } catch (error) {
      fail(error);
    } finally {
      setExporting(null);
    }
  };

  const columns: Column<ReportRow>[] = [
    {
      key: 'who',
      header: groupBy === 'holder' ? t('pricing.report.colHolder') : t('pricing.report.colCoupon'),
      render: (row) => (
        <span>
          {groupBy === 'holder' ? (
            <strong>{row.holder || t('pricing.report.noHolder')}</strong>
          ) : null}
          <span className="report-codes">
            {row.codes.map((entry) => (
              <button
                key={entry.code}
                type="button"
                className="report-code"
                onClick={(event) => {
                  // ⚠️  Not the row's own click: the row opens a coupon only when it IS one
                  event.stopPropagation();
                  onOpen(entry);
                }}
              >
                <code dir="ltr">{entry.code}</code>
              </button>
            ))}
          </span>
          {groupBy === 'coupon' && row.holder ? (
            <small className="coupon-holder">
              {t('pricing.holder')}: {row.holder}
            </small>
          ) : null}
        </span>
      ),
    },
    {
      key: 'uses',
      header: t('pricing.insights.uses'),
      align: 'end',
      secondary: true,
      render: (row) => count(row.uses),
    },
    {
      key: 'orders',
      header: t('pricing.report.colOrdersSplit'),
      render: (row) => (
        <span className="report-orders">
          <span>
            {t('pricing.report.registered')}:{' '}
            <strong>{row.registered === null ? '—' : count(row.registered)}</strong>
          </span>
          <span>
            {t('pricing.report.guest')}: <strong>{row.guest === null ? '—' : count(row.guest)}</strong>
          </span>
        </span>
      ),
    },
    {
      key: 'new',
      header: t('pricing.report.colNew'),
      align: 'end',
      secondary: true,
      render: (row) => (row.newCustomers === null ? '—' : count(row.newCustomers)),
    },
    {
      key: 'discount',
      header: t('pricing.insights.discount'),
      align: 'end',
      render: (row) => money(row.discount),
    },
    {
      key: 'net',
      header: t('pricing.insights.net'),
      align: 'end',
      render: (row) => <strong>{money(row.net)}</strong>,
    },
  ];

  return (
    <div className="report">
      {overview.data && !report.present ? (
        <Alert tone="info">{t('pricing.report.notAvailable')}</Alert>
      ) : null}

      {/* ── Summary cards ─────────────────────────── */}
      <div className="report-cards">
        <StatCard
          label={t('pricing.report.cardDiscount')}
          value={totals ? money(totals.discount_given) : '—'}
          hint={
            report.discountShare !== null
              ? t('pricing.report.shareOfGross', { rate: formatRate(report.discountShare, locale) })
              : ''
          }
          tone="warning"
          icon="%"
        />
        <StatCard
          label={t('pricing.report.cardSales')}
          value={totals ? money(totals.net_sales) : '—'}
          hint={totals ? t('pricing.insights.statSalesHint', { count: totals.orders }) : ''}
          tone="success"
          icon="◔"
        />
        <StatCard
          label={t('pricing.report.cardNew')}
          value={report.present ? count(report.newCustomers.count) : '—'}
          hint={
            report.present
              ? t('pricing.report.newHint', {
                  rate: formatRate(report.newCustomerRate, locale),
                  sales: money(report.newCustomers.net_sales),
                })
              : ''
          }
          icon="+"
        />
        <StatCard
          label={t('pricing.report.cardReturning')}
          value={report.present ? count(report.returningCustomers.count) : '—'}
          hint={
            report.present
              ? t('pricing.report.returningHint', { sales: money(report.returningCustomers.net_sales) })
              : ''
          }
          icon="↻"
        />
      </div>

      {/* ── Registered vs guest ───────────────────── */}
      {report.present ? (
        <div className="report-panels">
          <CouponCustomerSplit
            title={t('pricing.report.splitOrders')}
            registered={{
              weight: report.registered.orders,
              headline: `${t('pricing.insights.orders')}: ${count(report.registered.orders)}`,
              detail: `${t('pricing.insights.customers')}: ${count(report.registered.customers)} · ${money(report.registered.net)}`,
            }}
            guest={{
              weight: report.guest.orders,
              headline: `${t('pricing.insights.orders')}: ${count(report.guest.orders)}`,
              detail: `${t('pricing.insights.customers')}: ${count(report.guest.customers)} · ${money(report.guest.net)}`,
            }}
          />
          <CouponCustomerSplit
            title={t('pricing.report.splitDiscount')}
            registered={{
              weight: Number.parseFloat(report.discountByType.registered) || 0,
              headline: money(report.discountByType.registered),
            }}
            guest={{
              weight: Number.parseFloat(report.discountByType.guest) || 0,
              headline: money(report.discountByType.guest),
            }}
          />
        </div>
      ) : null}

      <p className="report-note">{t('pricing.report.help')}</p>

      <CouponTypeChart series={overview.data?.discount_series} />

      {/* ── By coupon / by holder ─────────────────── */}
      <section>
        <div className="report-toolbar">
          <h3>{t('pricing.report.tableTitle')}</h3>
          <div className="report-toolbar__actions">
            <Button
              size="sm"
              variant="secondary"
              loading={exporting === 'report'}
              onClick={() => {
                void runExport('report');
              }}
            >
              {t('pricing.report.exportReport')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={exporting === 'customers'}
              onClick={() => {
                void runExport('customers');
              }}
            >
              {t('pricing.report.exportCustomers')}
            </Button>
          </div>
        </div>

        <FilterBar
          hasFilters={Boolean(search)}
          onClear={() => {
            setSearch('');
            setPage(1);
          }}
        >
          <div className="report-groupby" role="group" aria-label={t('pricing.report.groupBy')}>
            {(['coupon', 'holder'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={groupBy === value}
                onClick={() => {
                  setGroupBy(value);
                  setPage(1);
                }}
              >
                {t(value === 'coupon' ? 'pricing.report.byCoupon' : 'pricing.report.byHolder')}
              </button>
            ))}
          </div>
          <FilterSearch
            value={search}
            onChange={(next) => {
              setSearch(next);
              setPage(1);
            }}
            placeholder={t('pricing.searchCoupons')}
          />
          <FilterSelect
            value={ordering === '-net_sales' ? '' : ordering}
            label={t('pricing.report.sortLabel')}
            options={SORTS.map((item) => ({ value: item.value, label: t(item.key) }))}
            onChange={(next) => {
              setOrdering(next || '-net_sales');
              setPage(1);
            }}
          />
        </FilterBar>

        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.key}
          isLoading={table.isPending}
          error={table.error}
          // ⚠️  Whole-row click only when the row IS one coupon; a holder with several codes
          //     offers each code as its own button instead of guessing which one was meant.
          onRowClick={(row) => {
            const only = row.codes.length === 1 ? row.codes[0] : undefined;
            if (only) onOpen(only);
          }}
          emptyTitle={t('pricing.report.noRows')}
          emptyBody={t('pricing.report.noRowsBody')}
        />

        {table.data ? (
          <Pagination page={table.data.page} pages={table.data.pages} onChange={setPage} />
        ) : null}
      </section>
    </div>
  );
}
