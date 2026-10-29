import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useReferralMember,
  type ReferralMembersParams,
  type ReferralRefereeRow,
} from '@/features/loyalty/api';
import { formatRate } from '@/portals/admin/components/reportFormat';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterSearch } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StatCard } from '@/shared/ui/StatCard';
import { StateMessage } from '@/shared/ui/StateMessage';
import { formatDate, formatMoney, formatNumber } from '@/shared/utils/format';

import './ReferralMembers.css';

export interface ReferralMemberTarget {
  id: string;
  name: string;
}

const STATUS_TONE: Record<string, 'success' | 'info' | 'danger' | 'warning'> = {
  REWARDED: 'success',
  QUALIFIED: 'success',
  PENDING: 'info',
  REJECTED: 'danger',
};

/**
 * The customers one member invited, and what became of each invitation.
 *
 * ⚠️  Remounted per member (`key`): the search box and the page number belong to one member's
 *     list, and carrying "page 3 of Dr. Sara's invitees" over to the next member opens an
 *     empty page.
 *
 * ⚠️  A status is a **word in a badge**, never only a colour, and a rejection shows its
 *     reason on the row — "rejected" with no reason sends the admin to another screen to
 *     answer the member's first question.
 */
export function ReferralMemberDrawer({
  target,
  period,
  onClose,
}: {
  target: ReferralMemberTarget | null;
  period: Pick<ReferralMembersParams, 'date_from' | 'date_to'>;
  onClose: () => void;
}) {
  return (
    <Drawer open={target !== null} onClose={onClose} {...(target ? { title: target.name } : {})}>
      {target ? <MemberBody key={target.id} target={target} period={period} /> : null}
    </Drawer>
  );
}

function MemberBody({
  target,
  period,
}: {
  target: ReferralMemberTarget;
  period: Pick<ReferralMembersParams, 'date_from' | 'date_to'>;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);

  const detail = useReferralMember(target.id, {
    ...period,
    ...(debounced ? { search: debounced } : {}),
    page,
  });

  if (detail.isPending) return <Spinner />;
  if (detail.error || !detail.data) {
    return <StateMessage icon="⚠" title={t('pricing.insights.loadError')} />;
  }

  const { summary, referees } = detail.data;

  const statusLabel = (status: string): string =>
    i18n.exists(`loyalty.referralReport.status.${status}`)
      ? t(`loyalty.referralReport.status.${status}`)
      : status;

  const columns: Column<ReferralRefereeRow>[] = [
    {
      key: 'referee',
      header: t('loyalty.referralReport.colInvitee'),
      render: (row) => (
        <span className="referral-member-cell">
          <strong>{row.referee.name || '—'}</strong>
          {row.referee.email ? <small dir="ltr">{row.referee.email}</small> : null}
          <small>
            {t('loyalty.referralReport.invitedOn')}: {formatDate(row.invited_at, locale)}
          </small>
        </span>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <span className="referral-member-cell">
          <Badge tone={STATUS_TONE[row.status] ?? 'neutral'}>{statusLabel(row.status)}</Badge>
          {row.status === 'REJECTED' && row.rejection_reason ? (
            <small>{row.rejection_reason}</small>
          ) : null}
          {row.rewarded_at ? (
            <small>
              {t('loyalty.rewardedAt')}: {formatDate(row.rewarded_at, locale)}
            </small>
          ) : null}
        </span>
      ),
    },
    {
      key: 'order',
      header: t('loyalty.referralReport.colOrder'),
      secondary: true,
      render: (row) =>
        row.qualifying_order_number ? <code dir="ltr">{row.qualifying_order_number}</code> : '—',
    },
    {
      key: 'sales',
      header: t('loyalty.referralReport.colSales'),
      align: 'end',
      render: (row) => (
        <span className="referral-member-cell">
          <strong>{formatMoney(row.net_sales, locale)}</strong>
          <small>
            {t('loyalty.referralReport.orders')}: {formatNumber(row.orders, locale)}
          </small>
        </span>
      ),
    },
  ];

  return (
    <div className="referral-member">
      <p className="referral-member__who">
        {summary.referrer.email ? <small dir="ltr">{summary.referrer.email}</small> : null}
        <small>
          {t('loyalty.referralReport.colCode')}: <code dir="ltr">{summary.code || '—'}</code>
        </small>
      </p>

      <div className="referral-member__cards">
        <StatCard
          label={t('loyalty.referralReport.colInvited')}
          value={formatNumber(summary.invited, locale)}
        />
        <StatCard
          label={t('loyalty.referralReport.colQualified')}
          value={formatNumber(summary.qualified, locale)}
          hint={`${t('loyalty.referralReport.colConversion')}: ${formatRate(summary.conversion_rate, locale)}`}
          tone="success"
        />
        <StatCard
          label={t('loyalty.referralReport.colPendingRejected')}
          value={`${formatNumber(summary.pending, locale)} / ${formatNumber(summary.rejected, locale)}`}
          hint={`${t('loyalty.referralReport.pending')} / ${t('loyalty.referralReport.rejected')}`}
        />
        <StatCard
          label={t('loyalty.referralReport.colSales')}
          value={formatMoney(summary.referee_net_sales, locale)}
          hint={`${t('loyalty.referralReport.orders')}: ${formatNumber(summary.referee_orders, locale)}`}
          tone="success"
        />
        <StatCard
          label={t('loyalty.referralReport.colPoints')}
          value={formatNumber(summary.points_awarded, locale)}
          tone="warning"
        />
      </div>

      <section>
        <h3>{t('loyalty.referralReport.invitees')}</h3>
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('loyalty.referralReport.searchInvitees')}
        />

        <DataTable
          columns={columns}
          rows={referees.results}
          rowKey={(row) => row.id}
          emptyTitle={t('loyalty.referralReport.noInvitees')}
        />
        <Pagination page={referees.page} pages={referees.pages} onChange={setPage} />
      </section>
    </div>
  );
}
