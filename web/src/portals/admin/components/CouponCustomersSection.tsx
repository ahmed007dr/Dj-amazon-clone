import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { downloadExport } from '@/features/exports/adminApi';
import {
  useCouponCustomers,
  type CouponCustomerRow,
  type CouponPeriod,
} from '@/features/pricing/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';
import { formatDate, formatMoney, formatNumber } from '@/shared/utils/format';

import './CouponInsights.css';
import './CouponReport.css';

/**
 * The people who used one coupon.
 *
 * ⚠️  **The badge says how the purchase was made, not what the person is today.**
 *     A guest who has since opened an account stays "Guest" for that purchase, with an
 *     "Has an account now" hint — folding them into "Registered" would move past sales
 *     between the two columns every time someone signs up.
 *
 * ⚠️  Search and sort are the server's (paginated lists are never filtered in the browser),
 *     and the export carries the same coupon, period and search as the list on screen.
 *
 * ⚠️  Contact details are shown as the server sent them — whatever masking it applies to
 *     this endpoint is not undone or second-guessed here.
 */
export function CouponCustomersSection({
  couponId,
  code,
  period,
}: {
  couponId: string;
  /** The coupon's code — the export dataset narrows by it (it has no coupon-id filter). */
  code: string;
  period: CouponPeriod;
}) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const locale = i18n.language;

  const [search, setSearch] = useState('');
  const [ordering, setOrdering] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const debounced = useDebounced(search);

  const customers = useCouponCustomers(couponId, {
    ...period,
    ...(debounced ? { search: debounced } : {}),
    ...(ordering ? { ordering } : {}),
    page,
  });

  const exportCustomers = async () => {
    setExporting(true);
    try {
      // ⚠️  The dataset's filters are period + a text search over code / name / holder, so the
      //     coupon is narrowed by its code. A code that is a prefix of another (SAVE10 / SAVE100)
      //     brings the longer one's buyers too — the file has a coupon column to tell them apart.
      await downloadExport('coupon_customers', {
        start: period.date_from ?? '',
        end: period.date_to ?? '',
        search: code,
      });
      notify(t('pricing.insights.exported'), 'success');
    } catch (error) {
      notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');
    } finally {
      setExporting(false);
    }
  };

  const columns: Column<CouponCustomerRow>[] = [
    {
      key: 'customer',
      header: t('pricing.insights.customer'),
      render: (row) => {
        const guestPurchase = (row.purchased_as || row.customer_type) === 'GUEST';
        return (
          <span className="report-customer">
            <strong>{row.name || '—'}</strong>
            {row.email ? (
              <small dir="ltr">{row.email}</small>
            ) : null}
            {row.phone ? (
              <small dir="ltr">{row.phone}</small>
            ) : null}
            <span className="report-customer__badges">
              <Badge tone={guestPurchase ? 'neutral' : 'success'}>
                {t(guestPurchase ? 'pricing.report.guest' : 'pricing.report.registered')}
              </Badge>
              {guestPurchase && row.has_account_now ? (
                <Badge tone="info">{t('pricing.report.hasAccountNow')}</Badge>
              ) : null}
              {row.is_new_customer ? (
                <Badge tone="warning">{t('pricing.report.newCustomer')}</Badge>
              ) : null}
            </span>
          </span>
        );
      },
    },
    {
      key: 'orders',
      header: t('pricing.insights.orders'),
      align: 'end',
      render: (row) => formatNumber(row.orders, locale),
    },
    {
      key: 'amounts',
      header: t('pricing.insights.net'),
      align: 'end',
      render: (row) => (
        <span>
          <strong>{formatMoney(row.net_sales, locale)}</strong>
          <small className="coupon-holder">
            {t('pricing.insights.discount')}: {formatMoney(row.discount, locale)}
          </small>
        </span>
      ),
    },
    {
      key: 'dates',
      header: t('pricing.report.colUsedBetween'),
      secondary: true,
      render: (row) => (
        <span>
          {row.first_used_at ? formatDate(row.first_used_at, locale) : '—'}
          <small className="coupon-holder">
            {row.last_used_at ? formatDate(row.last_used_at, locale) : '—'}
          </small>
        </span>
      ),
    },
  ];

  return (
    <section>
      <div className="report-customers__head">
        <h3>{t('pricing.report.customersTitle')}</h3>
        <Button
          size="sm"
          variant="secondary"
          loading={exporting}
          onClick={() => {
            void exportCustomers();
          }}
        >
          {t('pricing.report.exportCustomers')}
        </Button>
      </div>

      <div className="report-customers__head">
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('pricing.report.searchCustomers')}
        />
        <FilterSelect
          value={ordering}
          label={t('pricing.report.sortLabel')}
          options={[
            { value: '-net_sales', label: t('pricing.report.sortNet') },
            { value: '-orders', label: t('pricing.report.sortOrders') },
            { value: '-last_used_at', label: t('pricing.report.sortRecent') },
          ]}
          onChange={(next) => {
            setOrdering(next);
            setPage(1);
          }}
        />
      </div>

      <DataTable
        columns={columns}
        rows={customers.data?.results ?? []}
        rowKey={(row) => row.customer_key}
        isLoading={customers.isPending}
        error={customers.error}
        emptyTitle={t('pricing.report.noCustomers')}
        emptyBody={t('pricing.report.noCustomersBody')}
      />
      {customers.data ? (
        <Pagination page={customers.data.page} pages={customers.data.pages} onChange={setPage} />
      ) : null}
    </section>
  );
}
