import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminPoints,
  useAdminReferrals,
  useLoyaltyOverview,
  useLoyaltyPrograms,
  useReferralPrograms,
  useSaveReferralProgram,
  type AdminPointsEntry,
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

import './AdminLoyaltyPage.css';

type Tab = 'programs' | 'referral' | 'ledger';

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
 * لوحة الولاء والإحالة.
 *
 * ⚠️  **الالتزام أول رقم على الشاشة.**
 *
 *     عدد النقاط وحده رقم تسويقي يسرّ صاحب النشاط؛ وقيمتها
 *     بالجنيه هي ما يظهر في ميزانيته حين تُصرَف. وضعها ثانيةً
 *     يجعل قرار «ضاعِف النقاط» يُتخذ بلا رؤية تكلفته.
 */
export function AdminLoyaltyPage() {
  const { t } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('programs');
  const [page, setPage] = useState(1);

  const overview = useLoyaltyOverview();
  const programs = useLoyaltyPrograms();
  const referralPrograms = useReferralPrograms();
  const referrals = useAdminReferrals();
  const entries = useAdminPoints({ page });

  const saveReferral = useSaveReferralProgram();

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
      // ⚠️  الإشارة تُعرَض صراحةً: «٥٠» بلا إشارة لا يقول أكسبٌ
      //     هو أم سحب، والدفتر بلا اتجاه لا يُقرأ.
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
      <PageHeader title={t('loyalty.title')} subtitle={t('loyalty.subtitle')} />

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
        programs.isPending ? (
          <StateMessage icon="⏳" title={t('state.loading')} />
        ) : programs.data && programs.data.results.length > 0 ? (
          <div className="loyalty-programs">
            {programs.data.results.map((program) => (
              <LoyaltyProgramCard key={program.id} program={program} />
            ))}
          </div>
        ) : (
          <StateMessage
            icon="🎁"
            title={t('loyalty.noPrograms')}
            body={t('loyalty.noProgramsBody')}
          />
        )
      ) : null}

      {tab === 'referral' ? (
        <div className="loyalty-referral">
          {referralPrograms.data?.results.map((program) => (
            <article key={program.id} className="surface loyalty-referral__card">
              <header>
                <h3>{program.name_ar}</h3>
                {/* ⚠️  نفس المفتاح ونفس المكان في البطاقتين: مكانان
                    مختلفان لنفس القرار يجعل الأدمن يبحث في كل مرة. */}
                <label className="loyalty-switch">
                  <input
                    type="checkbox"
                    checked={program.is_active}
                    disabled={saveReferral.isPending}
                    onChange={(event) =>
                      saveReferral.mutate(
                        { id: program.id, is_active: event.target.checked },
                        { onError: fail },
                      )
                    }
                  />
                  <span className="loyalty-switch__track" aria-hidden />
                  <span className="loyalty-switch__text">
                    {program.is_active ? t('loyalty.on') : t('loyalty.off')}
                  </span>
                </label>
              </header>

              <dl className="loyalty-program__facts">
                <div>
                  <dt>{t('loyalty.referrerPoints')}</dt>
                  <dd dir="ltr">{program.referrer_points}</dd>
                </div>
                <div>
                  <dt>{t('loyalty.refereePoints')}</dt>
                  <dd dir="ltr">{program.referee_points}</dd>
                </div>
                <div>
                  <dt>{t('loyalty.minOrder')}</dt>
                  <dd dir="ltr">{program.min_order_amount}</dd>
                </div>
                <div>
                  <dt>{t('loyalty.referralCap')}</dt>
                  <dd dir="ltr">
                    {program.max_referrals_per_user > 0
                      ? program.max_referrals_per_user
                      : t('loyalty.noCap')}
                  </dd>
                </div>
              </dl>
            </article>
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
