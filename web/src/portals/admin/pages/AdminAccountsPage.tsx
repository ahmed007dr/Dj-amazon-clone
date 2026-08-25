import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  getOnlineNow,
  listAccounts,
  type AdminAccount,
} from '@/features/administration/api';
import { SuspendAccountModal } from '@/features/administration/components/SuspendAccountModal';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { AccountHistoryDrawer } from '@/portals/admin/components/AccountHistoryDrawer';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatCard } from '@/shared/ui/StatCard';
import { formatDateTime, formatRelative } from '@/shared/utils/format';

import './AdminAccountsPage.css';

const ACCOUNT_TYPES = [
  'GUEST',
  'STUDENT',
  'DOCTOR',
  'PHARMACIST',
  'PHARMACY',
  'WAREHOUSE',
  'TRADER',
  'SUPPLIER',
  'EMPLOYEE',
  'ADMIN',
];

/**
 * Accounts and monitoring.
 *
 * ⚠️  "Who is using the system now" refreshes automatically every half minute.
 *
 *     A monitoring screen that does not update is not monitoring — and an admin
 *     seeing a static list assumes nobody has logged in, while the screen is an
 *     hour old.
 */
export function AdminAccountsPage() {
  const { t, i18n } = useTranslation();

  const [search, setSearch] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<AdminAccount | null>(null);
  const [historyOf, setHistoryOf] = useState<AdminAccount | null>(null);

  const debouncedSearch = useDebounced(search);

  const accounts = useQuery({
    queryKey: ['admin', 'accounts', debouncedSearch, type, status, page],
    queryFn: () =>
      listAccounts({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(type ? { account_type: type } : {}),
        ...(status ? { status } : {}),
        page,
      }),
    staleTime: 30 * 1000,
  });

  const online = useQuery({
    queryKey: ['admin', 'online-now'],
    queryFn: getOnlineNow,
    // ⚠️  The polling is what makes it monitoring rather than a snapshot
    refetchInterval: 30 * 1000,
    staleTime: 0,
  });

  const columns: Column<AdminAccount>[] = [
    {
      key: 'user',
      header: t('admin.user'),
      render: (account) => (
        <span className="account-cell">
          <strong>{account.full_name || '—'}</strong>
          <span className="muted" style={{ direction: 'ltr' }}>
            {account.email}
          </span>
        </span>
      ),
    },
    {
      key: 'type',
      header: t('auth.accountType'),
      render: (account) => t(`accountType.${account.account_type}`),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (account) => (
        <Badge
          tone={
            account.status === 'ACTIVE'
              ? 'success'
              : account.status === 'BLOCKED'
                ? 'danger'
                : 'warning'
          }
        >
          {t(`accountStatus.${account.status}`)}
        </Badge>
      ),
    },
    {
      key: 'verification',
      header: t('account.verificationStatus'),
      render: (account) => t(`verification.${account.verification_status}`),
    },
    {
      key: 'seen',
      header: t('admin.lastSeen'),
      render: (account) =>
        account.is_online ? (
          <Badge tone="success">{t('admin.onlineNow')}</Badge>
        ) : account.last_seen ? (
          formatRelative(account.last_seen, i18n.language)
        ) : (
          '—'
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (account) => (
        <div className="admin-accounts__actions">
          {/* ⚠️  "History" before "suspend": whoever is about to suspend an account
              needs to see what its owner did first — and the order leads to
              reading before deciding. */}
          <Button variant="ghost" size="sm" onClick={() => setHistoryOf(account)}>
            {t('admin.history.title')}
          </Button>

          <Button
            variant={account.status === 'ACTIVE' ? 'secondary' : 'primary'}
            size="sm"
            onClick={() => {
              setTarget(account);
            }}
          >
            {account.status === 'ACTIVE' ? t('admin.suspend') : t('admin.activate')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('nav.users')}
        {...(accounts.data ? { description: t('admin.total', { count: accounts.data.count }) } : {})}
      />

      <div className="admin-accounts__stats">
        <StatCard
          label={t('admin.onlineNow')}
          value={online.data?.count ?? 0}
          hint={t('admin.onlineHint')}
          tone="success"
          icon="●"
        />
        <StatCard
          label={t('admin.total', { count: accounts.data?.count ?? 0 })}
          value={accounts.data?.count ?? 0}
          icon="▤"
        />
      </div>

      {online.data && online.data.count > 0 ? (
        <section className="surface admin-accounts__online">
          <h2 className="admin-accounts__heading">{t('admin.whoIsOnline')}</h2>
          <ul className="admin-accounts__list">
            {online.data.users.map((user) => (
              <li key={user.id}>
                <strong>{user.full_name || user.email}</strong>
                <span className="muted">{t(`accountType.${user.account_type}`)}</span>
                <span className="muted">
                  {formatDateTime(user.last_seen, i18n.language)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <FilterBar
        hasFilters={Boolean(search || type || status)}
        onClear={() => {
          setSearch('');
          setType('');
          setStatus('');
          setPage(1);
        }}
      >
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('admin.searchAccounts')}
        />

        <FilterSelect
          value={type}
          label={t('auth.accountType')}
          options={ACCOUNT_TYPES.map((value) => ({ value, label: t(`accountType.${value}`) }))}
          onChange={(next) => {
            setType(next);
            setPage(1);
          }}
        />

        <FilterSelect
          value={status}
          label={t('admin.status')}
          options={['ACTIVE', 'SUSPENDED', 'BLOCKED'].map((value) => ({
            value,
            label: t(`accountStatus.${value}`),
          }))}
          onChange={(next) => {
            setStatus(next);
            setPage(1);
          }}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={accounts.data?.results ?? []}
        rowKey={(account) => account.id}
        isLoading={accounts.isPending}
        error={accounts.error}
      />

      {accounts.data ? (
        <Pagination page={accounts.data.page} pages={accounts.data.pages} onChange={setPage} />
      ) : null}

      <SuspendAccountModal
        account={target}
        onClose={() => {
          setTarget(null);
        }}
      />

      <AccountHistoryDrawer account={historyOf} onClose={() => setHistoryOf(null)} />
    </>
  );
}
