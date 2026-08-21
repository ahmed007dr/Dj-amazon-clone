import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminPoints,
  useAdminReferrals,
  useExpirePoints,
  useLoyaltyOverview,
  useLoyaltyPrograms,
  useReferralPrograms,
  type AdminPointsEntry,
  type PointsKind,
  type Referral,
} from '@/features/loyalty/api';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';
import { StatCard } from '@/shared/ui/StatCard';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useToast } from '@/shared/ui/useToast';
import { LoyaltyProgramCard } from '@/portals/admin/components/LoyaltyProgramCard';
import { NewProgramForm } from '@/portals/admin/components/NewProgramForm';
import { PointsAdjustPanel } from '@/portals/admin/components/PointsAdjustPanel';
import { ReferralProgramCard } from '@/portals/admin/components/ReferralProgramCard';

import './AdminLoyaltyPage.css';

type Tab = 'programs' | 'referral' | 'ledger';

const LEDGER_KINDS: PointsKind[] = [
  'EARN',
  'REDEEM',
  'REFERRAL',
  'EXPIRE',
  'REVERSE',
  'ADJUSTMENT',
  'DEDUCTION',
];

const REFERRAL_STATUSES = ['PENDING', 'REWARDED', 'REJECTED'] as const;

const KIND_TONE: Record<string, 'success' | 'danger' | 'neutral' | 'info'> = {
  EARN: 'success',
  REFERRAL: 'success',
  ADJUSTMENT: 'info',
  REDEEM: 'neutral',
  EXPIRE: 'neutral',
  REVERSE: 'danger',
  DEDUCTION: 'danger',
};

const REFERRAL_TONE: Record<string, 'success' | 'info' | 'danger'> = {
  REWARDED: 'success',
  PENDING: 'info',
  REJECTED: 'danger',
};

/**
 * The loyalty and referral panel.
 *
 * ⚠️  **The liability is the first figure on the screen.**
 *
 *     The number of points alone is a marketing figure that pleases the
 *     business owner; and its value in pounds is what appears on their balance
 *     sheet when it is redeemed. Putting it second makes the "double the
 *     points" decision get taken without seeing its cost.
 */
export function AdminLoyaltyPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('programs');
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [kindFilter, setKindFilter] = useState('');
  const [referralStatus, setReferralStatus] = useState('');

  const overview = useLoyaltyOverview();
  const programs = useLoyaltyPrograms();
  const referralPrograms = useReferralPrograms();
  const referrals = useAdminReferrals(referralStatus || undefined);
  const entries = useAdminPoints({ page, ...(kindFilter ? { kind: kindFilter } : {}) });

  const expire = useExpirePoints();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  if (isApiError(overview.error) && overview.error.status === 403) {
    return (
      <>
        <PageHeader title={t('loyalty.title')} />
        <StateMessage icon="🔒" title={t('staff.noAccess')} body={t('staff.noAccessBody')} />
      </>
    );
  }

  const entryColumns: Column<AdminPointsEntry>[] = [
    {
      key: 'customer',
      header: t('loyalty.customer'),
      render: (row) => <strong>{row.customer_name}</strong>,
    },
    {
      key: 'kind',
      header: t('loyalty.kind'),
      render: (row) => <Badge tone={KIND_TONE[row.kind] ?? 'neutral'}>{row.kind_display}</Badge>,
    },
    {
      key: 'points',
      header: t('loyalty.points'),
      align: 'end',
      // ⚠️  The sign is displayed explicitly: "50" with no sign does not say whether
      //     it is an earning or a withdrawal, and a ledger with no direction cannot be read.
      render: (row) => (
        <strong dir="ltr" className={row.signed_points > 0 ? 'points-up' : 'points-down'}>
          {row.signed_points > 0 ? `+${row.signed_points}` : row.signed_points}
        </strong>
      ),
    },
    {
      key: 'reference',
      header: t('loyalty.reference'),
      secondary: true,
      render: (row) => <code dir="ltr">{row.order_number ?? row.reference ?? '—'}</code>,
    },
    {
      key: 'expires',
      header: t('loyalty.expiresOn'),
      secondary: true,
      render: (row) => <span dir="ltr">{row.expires_on ?? '—'}</span>,
    },
    {
      key: 'note',
      header: t('loyalty.note'),
      secondary: true,
      render: (row) => (
        <span className="loyalty-note-cell">
          {row.note || '—'}
          {row.recorded_by_name ? <em>{row.recorded_by_name}</em> : null}
        </span>
      ),
    },
  ];

  const referralColumns: Column<Referral>[] = [
    { key: 'referrer', header: t('loyalty.referrer'), render: (row) => row.referrer_name },
    { key: 'referee', header: t('loyalty.referee'), render: (row) => row.referee_name },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={REFERRAL_TONE[row.status] ?? 'neutral'}>{row.status_display}</Badge>
      ),
    },
    {
      key: 'rewarded',
      header: t('loyalty.rewardedAt'),
      secondary: true,
      render: (row) => <span dir="ltr">{row.rewarded_at?.slice(0, 10) ?? '—'}</span>,
    },
  ];

  return (
    <>
      <PageHeader title={t('loyalty.title')} description={t('loyalty.subtitle')} />

      <div className="loyalty-stats">
        <StatCard
          label={t('loyalty.liability')}
          value={<span dir="ltr">{overview.data?.liability.value ?? '—'}</span>}
          hint={t('loyalty.liabilityHint', { points: overview.data?.liability.points ?? 0 })}
          tone="warning"
          icon="💳"
        />
        <StatCard
          label={t('loyalty.activePrograms')}
          value={overview.data?.active_programs ?? '—'}
          hint={t('loyalty.activeProgramsHint')}
          tone={overview.data?.active_programs ? 'success' : 'neutral'}
          icon="🎯"
        />
        <StatCard
          label={t('loyalty.members')}
          value={overview.data?.members ?? '—'}
          hint={t('loyalty.membersHint')}
          icon="👥"
        />
        <StatCard
          label={t('loyalty.activeReferral')}
          value={overview.data?.active_referral_programs ?? '—'}
          hint={t('loyalty.activeReferralHint')}
          icon="🤝"
        />
      </div>

      <div className="loyalty-tabs" role="tablist">
        {(['programs', 'referral', 'ledger'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'is-active' : ''}
            onClick={() => setTab(value)}
          >
            {t(`loyalty.tab.${value}`)}
          </button>
        ))}
      </div>

      {tab === 'programs' ? (
        <>
          <div className="loyalty-toolbar">
            {!creating ? (
              <Button size="sm" onClick={() => setCreating(true)}>
                {t('loyalty.newProgram')}
              </Button>
            ) : null}

            {/* ⚠️  Expiring the due points is a button, not merely a nightly job.
                Whoever closes the month needs to see the liability after the
                expiry rather than before — and waiting for midnight is not an option then. */}
            <Button
              size="sm"
              variant="ghost"
              loading={expire.isPending}
              onClick={() => {
                if (!window.confirm(t('loyalty.confirmExpire'))) return;
                expire.mutate(undefined, {
                  onSuccess: (data) =>
                    notify(
                      data.batches > 0
                        ? t('loyalty.expired', { points: data.points, batches: data.batches })
                        : t('loyalty.nothingExpired'),
                      'success',
                    ),
                  onError: fail,
                });
              }}
            >
              {t('loyalty.expireNow')}
            </Button>
          </div>

          {creating ? (
            <div className="loyalty-programs">
              <NewProgramForm kind="loyalty" onDone={() => setCreating(false)} />
            </div>
          ) : null}

          {programs.isPending ? (
            <StateMessage icon="⏳" title={t('state.loading')} />
          ) : programs.data && programs.data.results.length > 0 ? (
            <div className="loyalty-programs">
              {programs.data.results.map((program) => (
                <LoyaltyProgramCard key={program.id} program={program} />
              ))}
            </div>
          ) : !creating ? (
            <StateMessage
              icon="🎁"
              title={t('loyalty.noPrograms')}
              body={t('loyalty.noProgramsBody')}
            />
          ) : null}
        </>
      ) : null}

      {tab === 'referral' ? (
        <div className="loyalty-referral">
          <div className="loyalty-toolbar">
            {!creating ? (
              <Button size="sm" onClick={() => setCreating(true)}>
                {t('loyalty.newReferralProgram')}
              </Button>
            ) : null}

            <label className="loyalty-filter">
              {t('admin.status')}
              <select
                value={referralStatus}
                onChange={(event) => setReferralStatus(event.target.value)}
              >
                <option value="">{t('loyalty.allStatuses')}</option>
                {REFERRAL_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {t(`loyalty.referralStatus.${value}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {creating ? <NewProgramForm kind="referral" onDone={() => setCreating(false)} /> : null}

          {referralPrograms.data?.results.map((program) => (
            <ReferralProgramCard key={program.id} program={program} />
          ))}

          <DataTable
            columns={referralColumns}
            rows={referrals.data?.results ?? []}
            isLoading={referrals.isPending}
            error={referrals.error}
            rowKey={(row) => row.id}
            emptyTitle={t('loyalty.noReferrals')}
          />
        </div>
      ) : null}

      {tab === 'ledger' ? (
        <>
          <PointsAdjustPanel />

          <div className="loyalty-toolbar">
            <label className="loyalty-filter">
              {t('loyalty.kind')}
              <select
                value={kindFilter}
                onChange={(event) => {
                  setKindFilter(event.target.value);
                  // ⚠️  Returning to the first page with every filter change: staying
                  //     on page 7 after filtering gives an empty table that reads
                  //     as "no results" when there are results.
                  setPage(1);
                }}
              >
                <option value="">{t('loyalty.allKinds')}</option>
                {LEDGER_KINDS.map((value) => (
                  <option key={value} value={value}>
                    {t(`loyalty.pointsKind.${value}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <DataTable
            columns={entryColumns}
            rows={entries.data?.results ?? []}
            isLoading={entries.isPending}
            error={entries.error}
            rowKey={(row) => row.id}
            emptyTitle={t('loyalty.noEntries')}
            emptyBody={t('loyalty.noEntriesBody')}
          />
          {entries.data ? (
            <Pagination page={entries.data.page} pages={entries.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : null}
    </>
  );
}
