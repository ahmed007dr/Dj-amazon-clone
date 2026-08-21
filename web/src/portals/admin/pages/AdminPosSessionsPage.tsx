import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Session } from '@/features/pos/api';
import { useAdminRegisters, useAdminSession, useAdminSessions } from '@/features/pos/adminApi';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { RegistersPanel } from '@/portals/admin/components/RegistersPanel';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { Spinner } from '@/shared/ui/Spinner';
import { FilterBar, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { formatDate } from '@/shared/utils/format';

import './AdminPosSessionsPage.css';

/**
 * Point-of-sale shifts.
 *
 * ⚠️  **The screen is read by the discrepancy column first — and was built for that.**
 *
 *     The admin does not open it to browse shifts but to find the non-zero cash
 *     discrepancy. A list showing everything at the same weight buries the
 *     shift a hundred pounds short among thirty balanced ones — so nobody sees
 *     it until the shortfall recurs for a month.
 */

/** ⚠️  A discrepancy larger than this is highlighted visually — it mirrors `pos.cash_variance_threshold`. */
const NOTABLE_VARIANCE = 20;

export function AdminPosSessionsPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [status, setStatus] = useState('');
  const [register, setRegister] = useState('');
  const [page, setPage] = useState(1);
  const [detailOf, setDetailOf] = useState<string | null>(null);
  const [view, setView] = useState<'sessions' | 'registers'>('sessions');

  const detail = useAdminSession(detailOf);

  const registers = useAdminRegisters();
  const query = useAdminSessions({
    ...(status ? { status } : {}),
    ...(register ? { register } : {}),
    page,
  });

  const columns: Column<Session>[] = [
    {
      key: 'number',
      header: t('pos.sessionNumber'),
      render: (session) => <strong dir="ltr">{session.number}</strong>,
    },
    {
      key: 'register',
      header: t('pos.register'),
      render: (session) => session.register_code,
    },
    {
      key: 'cashier',
      header: t('pos.cashier'),
      render: (session) => session.cashier_name,
    },
    {
      key: 'opened',
      header: t('pos.openedAt'),
      secondary: true,
      render: (session) => formatDate(session.opened_at, i18n.language),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (session) =>
        session.status === 'OPEN' ? (
          <Badge tone="info">{t('pos.open')}</Badge>
        ) : (
          <Badge tone="neutral">{t('pos.closed')}</Badge>
        ),
    },
    {
      key: 'counted',
      header: t('pos.counted'),
      align: 'end',
      secondary: true,
      // ⚠️  A dash rather than zero for an open shift: zero is a figure read as a count
      //     that happened and came to nothing, and the difference between them is the whole meaning.
      render: (session) => <span dir="ltr">{session.counted_cash ?? '—'}</span>,
    },
    {
      key: 'variance',
      header: t('pos.variance'),
      align: 'end',
      render: (session) => <VarianceCell session={session} />,
    },
  ];

  return (
    <>
      <PageHeader title={t('pos.sessions')} />

      {/* ⚠️  The registers are here rather than in "system": whoever reads a branch's
          shifts is who adds its second register and disables the broken one —
          and separating them makes opening a new branch a journey between two screens. */}
      <div className="pos-view-tabs" role="tablist">
        {(['sessions', 'registers'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={view === value}
            className={view === value ? 'is-active' : ''}
            onClick={() => setView(value)}
          >
            {t(`pos.view.${value}`)}
          </button>
        ))}
      </div>

      {view === 'registers' ? <RegistersPanel /> : null}

      {view === 'sessions' ? (
      <>
      <FilterBar>
        <FilterSelect
          label={t('admin.status')}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          // ⚠️  No "all" option: `FilterSelect` adds it itself
          //     as an empty option carrying the label — and adding it here duplicates it.
          options={[
            { value: 'OPEN', label: t('pos.open') },
            { value: 'CLOSED', label: t('pos.closed') },
          ]}
        />

        <FilterSelect
          label={t('pos.register')}
          value={register}
          onChange={(value) => {
            setRegister(value);
            setPage(1);
          }}
          options={(registers.data ?? []).map((row) => ({
            value: row.id,
            label: localized(row, 'name'),
          }))}
        />
      </FilterBar>

      <DataTable
        columns={[
          ...columns,
          {
            key: 'actions',
            header: '',
            align: 'end',
            // ⚠️  The detail is requested rather than fetched for every row: the page shows
            //     twenty shifts and one of them gets read.
            render: (row) => (
              <Button size="sm" variant="ghost" onClick={() => setDetailOf(row.id)}>
                {t('pos.sessionDetail')}
              </Button>
            ),
          },
        ]}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(session) => session.id}
        emptyTitle={t('pos.noSessions')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
      </>
      ) : null}

      <Drawer
        open={detailOf !== null}
        onClose={() => setDetailOf(null)}
        {...(detail.data ? { title: detail.data.number } : {})}
      >
        {detail.isPending ? (
          <Spinner />
        ) : detail.data ? (
          <dl className="session-detail">
            {(
              [
                ['pos.register', detail.data.register_code],
                ['pos.cashier', detail.data.cashier_name],
                ['pos.openingFloat', detail.data.opening_float],
                ['pos.countedCash', detail.data.counted_cash ?? '—'],
                ['pos.expectedCash', detail.data.expected_cash ?? '—'],
                ['pos.variance', detail.data.variance ?? '—'],
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt>{t(key)}</dt>
                <dd dir="ltr">{value}</dd>
              </div>
            ))}

            {/* ⚠️  The discrepancy's explanation is the content, not a footnote: a
                shift with a discrepancy and no explanation is exactly what the review is looking for. */}
            {detail.data.variance_note ? (
              <div className="session-detail__note">
                <dt>{t('pos.varianceNote')}</dt>
                <dd>{detail.data.variance_note}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </Drawer>
    </>
  );
}

/**
 * The discrepancy cell.
 *
 * ⚠️  **The colour is not the only signal.**
 *
 *     Red with no text disappears entirely for anyone who cannot distinguish
 *     colours — and this is the case that is meant to be caught at a glance.
 *     The signal here is the colour **and the bold weight and the sign** together.
 */
function VarianceCell({ session }: { session: Session }) {
  if (session.variance === null) return <span>—</span>;

  const value = Number(session.variance);
  const notable = Math.abs(value) >= NOTABLE_VARIANCE;

  return (
    <span
      dir="ltr"
      className={`pos-variance ${notable ? 'is-notable' : ''} ${
        value < 0 ? 'is-short' : ''
      }`}
    >
      {value > 0 ? `+${session.variance}` : session.variance}
    </span>
  );
}
