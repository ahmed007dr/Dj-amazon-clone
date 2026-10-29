import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { downloadExport } from '@/features/exports/adminApi';
import {
  useReferralMembers,
  useReferralPrograms,
  type ReferralMemberRow,
} from '@/features/loyalty/api';
import { periodParams, isInvertedRange, ALL_TIME, type PeriodState } from '@/portals/admin/components/couponPeriod';
import { CouponPeriodFilter } from '@/portals/admin/components/CouponStatsBar';
import { ReferralMemberDrawer } from '@/portals/admin/components/ReferralMemberDrawer';
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
import { formatDate, formatMoney, formatNumber } from '@/shared/utils/format';

import './ReferralMembers.css';

const SORTS = [
  { value: '-qualified', key: 'loyalty.referralReport.sortQualified' },
  { value: '-invited', key: 'loyalty.referralReport.sortInvited' },
  { value: '-referee_net_sales', key: 'loyalty.referralReport.sortSales' },
  { value: '-conversion_rate', key: 'loyalty.referralReport.sortConversion' },
  { value: '-points_awarded', key: 'loyalty.referralReport.sortPoints' },
  { value: '-last_invited_at', key: 'loyalty.referralReport.sortRecent' },
];

/**
 * "Referral members": which members brought customers in, and what those customers were worth.
 *
 * ⚠️  **One row per member, not per invitation.** The existing referral list answers "who
 *     invited whom"; the owner's question is "through which members did new customers
 *     arrive?" — a ranked list of members, with the invited people one click away.
 *
 * ⚠️  **Historical data stays visible when the programme is switched off.** Pausing a campaign
 *     must not make its results vanish; an info banner says the programme is off and the
 *     figures are what it already brought in.
 *
 * ⚠️  The rates (`conversion_rate`) are the server's own numbers — displayed, never divided
 *     again here, so the screen and the export cannot disagree.
 */
export function ReferralMembersReport() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const locale = i18n.language;

  const [period, setPeriod] = useState<PeriodState>(ALL_TIME);
  const [search, setSearch] = useState('');
  const [ordering, setOrdering] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [open, setOpen] = useState<{ id: string; name: string } | null>(null);
  const debounced = useDebounced(search);

  const invalid = isInvertedRange(period);
  const range = periodParams(period);

  const programs = useReferralPrograms();
  const members = useReferralMembers(
    {
      ...range,
      ...(debounced ? { search: debounced } : {}),
      ...(ordering ? { ordering } : {}),
      page,
    },
    !invalid,
  );

  const totals = members.data?.totals;
  const programOff =
    programs.data !== undefined && !programs.data.results.some((program) => program.is_active);

  const exportMembers = async () => {
    setExporting(true);
    try {
      await downloadExport('referral_members', {
        start: range.date_from ?? '',
        end: range.date_to ?? '',
        search: debounced,
      });
      notify(t('pricing.insights.exported'), 'success');
    } catch (error) {
      notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');
    } finally {
      setExporting(false);
    }
  };

  const columns: Column<ReferralMemberRow>[] = [
    {
      key: 'member',
      header: t('loyalty.referralReport.colMember'),
      render: (row) => (
        <span className="referral-member-cell">
          <strong>{row.referrer.name || '—'}</strong>
          {row.referrer.email ? <small dir="ltr">{row.referrer.email}</small> : null}
          <small>
            {t('loyalty.referralReport.colCode')}: <code dir="ltr">{row.code || '—'}</code>
          </small>
        </span>
      ),
    },
    {
      key: 'invited',
      header: t('loyalty.referralReport.colInvited'),
      align: 'end',
      render: (row) => formatNumber(row.invited, locale),
    },
    {
      key: 'qualified',
      header: t('loyalty.referralReport.colQualified'),
      align: 'end',
      render: (row) => <strong>{formatNumber(row.qualified, locale)}</strong>,
    },
    {
      key: 'open',
      header: t('loyalty.referralReport.colPendingRejected'),
      align: 'end',
      secondary: true,
      // ⚠️  Pending and rejected share a cell: both are "did not convert (yet)", and the table
      //     is already seven columns wide at 1280px.
      render: (row) => (
        <span className="referral-member-cell">
          <span>
            {t('loyalty.referralReport.pending')}: {formatNumber(row.pending, locale)}
          </span>
          <span>
            {t('loyalty.referralReport.rejected')}: {formatNumber(row.rejected, locale)}
          </span>
        </span>
      ),
    },
    {
      key: 'conversion',
      header: t('loyalty.referralReport.colConversion'),
      align: 'end',
      render: (row) => formatRate(row.conversion_rate, locale),
    },
    {
      key: 'sales',
      header: t('loyalty.referralReport.colSales'),
      align: 'end',
      render: (row) => (
        <span className="referral-member-cell">
          <strong>{formatMoney(row.referee_net_sales, locale)}</strong>
          <small>
            {t('loyalty.referralReport.orders')}: {formatNumber(row.referee_orders, locale)}
          </small>
        </span>
      ),
    },
    {
      key: 'points',
      header: t('loyalty.referralReport.colPoints'),
      align: 'end',
      secondary: true,
      render: (row) => (
        <span className="referral-member-cell">
          <strong>{formatNumber(row.points_awarded, locale)}</strong>
          <small>
            {t('loyalty.referralReport.lastInvite')}:{' '}
            {row.last_invited_at ? formatDate(row.last_invited_at, locale) : '—'}
          </small>
        </span>
      ),
    },
  ];

  return (
    <div className="referral-report">
      {programOff ? <Alert tone="info">{t('loyalty.referralReport.programOff')}</Alert> : null}
      {invalid ? <Alert tone="warning">{t('pricing.insights.invertedRange')}</Alert> : null}
      {members.error ? <Alert tone="danger">{t('pricing.insights.loadError')}</Alert> : null}

      <CouponPeriodFilter
        value={period}
        onChange={(next) => {
          setPeriod(next);
          setPage(1);
        }}
      />

      <div className="referral-report__cards">
        <StatCard
          label={t('loyalty.referralReport.cardMembers')}
          value={totals ? formatNumber(totals.members, locale) : '—'}
          hint={t('loyalty.referralReport.cardMembersHint')}
          icon="👥"
        />
        <StatCard
          label={t('loyalty.referralReport.cardInvited')}
          value={totals ? formatNumber(totals.invited, locale) : '—'}
          hint={t('loyalty.referralReport.cardInvitedHint')}
          icon="✉"
        />
        <StatCard
          label={t('loyalty.referralReport.cardQualified')}
          value={totals ? formatNumber(totals.qualified, locale) : '—'}
          hint={
            totals
              ? t('loyalty.referralReport.cardQualifiedHint', {
                  invited: formatNumber(totals.invited, locale),
                })
              : ''
          }
          tone="success"
          icon="✓"
        />
        <StatCard
          label={t('loyalty.referralReport.cardSales')}
          value={
            totals
              ? formatMoney(totals.referee_net_sales ?? totals.new_customer_sales ?? '0', locale)
              : '—'
          }
          hint={t('loyalty.referralReport.cardSalesHint')}
          tone="success"
          icon="◔"
        />
        <StatCard
          label={t('loyalty.referralReport.cardPoints')}
          value={totals ? formatNumber(totals.points_awarded, locale) : '—'}
          hint={t('loyalty.referralReport.cardPointsHint')}
          tone="warning"
          icon="★"
        />
      </div>

      <p className="referral-report__note">{t('loyalty.referralReport.help')}</p>

      <FilterBar
        hasFilters={Boolean(search || ordering)}
        onClear={() => {
          setSearch('');
          setOrdering('');
          setPage(1);
        }}
      >
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('loyalty.referralReport.search')}
        />
        <FilterSelect
          value={ordering}
          label={t('loyalty.referralReport.sortLabel')}
          options={SORTS.map((item) => ({ value: item.value, label: t(item.key) }))}
          onChange={(next) => {
            setOrdering(next);
            setPage(1);
          }}
        />
        <Button
          size="sm"
          variant="secondary"
          loading={exporting}
          onClick={() => {
            void exportMembers();
          }}
        >
          {t('loyalty.referralReport.export')}
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={members.data?.results ?? []}
        rowKey={(row) => row.referrer.id}
        isLoading={members.isPending && !invalid}
        error={members.error}
        onRowClick={(row) => {
          setOpen({ id: row.referrer.id, name: row.referrer.name });
        }}
        emptyTitle={t('loyalty.referralReport.empty')}
        emptyBody={t('loyalty.referralReport.emptyBody')}
      />

      {members.data ? (
        <Pagination page={members.data.page} pages={members.data.pages} onChange={setPage} />
      ) : null}

      <ReferralMemberDrawer
        target={open}
        period={range}
        onClose={() => {
          setOpen(null);
        }}
      />
    </div>
  );
}
