import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSuppliers, type Supplier } from '@/features/suppliers/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { ReorderPanel } from '@/portals/admin/components/ReorderPanel';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StateMessage } from '@/shared/ui/StateMessage';

import { SupplierPanel } from '../components/SupplierPanel';

import './AdminSuppliersPage.css';

/**
 * Suppliers.
 *
 * ⚠️  **The balance and total purchases are in the list itself.**
 *
 *     Whoever opens this screen opens it to learn "how much do we owe whom?"
 *     before anything else. Burying them in the details forces them to open
 *     every supplier to find who is due payment — which is what the screen is
 *     opened for.
 *
 * ⚠️  And the two figures come from **an aggregation in a single query** rather
 *     than a call per row: computing per supplier separately was one query per line.
 */
export function AdminSuppliersPage() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [hasDebt, setHasDebt] = useState(false);
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
  const [view, setView] = useState<'suppliers' | 'reorder'>('suppliers');
  const [selected, setSelected] = useState<Supplier | null>(null);

  const debounced = useDebounced(search);
  const query = useSuppliers({
    ...(debounced ? { search: debounced } : {}),
    ...(status ? { status } : {}),
    ...(hasDebt ? { has_debt: 'true' } : {}),
    ...(overdue ? { overdue: 'true' } : {}),
    page,
  });

  if (isApiError(query.error) && query.error.status === 403) {
    return (
      <>
        <PageHeader title={t('suppliers.title')} />
        <StateMessage
          icon="🔒"
          title={t('suppliers.noAccess')}
          body={t('suppliers.noAccessBody')}
        />
      </>
    );
  }

  const reset = () => setPage(1);

  const columns: Column<Supplier>[] = [
    {
      key: 'name',
      header: t('suppliers.supplier'),
      render: (row) => (
        <div className="supplier-cell">
          <strong>{localized(row, 'name')}</strong>
          <code>{row.code}</code>
        </div>
      ),
    },
    {
      key: 'contact',
      header: t('suppliers.contact'),
      secondary: true,
      render: (row) => (
        <div className="supplier-cell">
          <span>{row.contact_person || '—'}</span>
          <span dir="ltr" className="supplier-muted">
            {row.phone || '—'}
          </span>
        </div>
      ),
    },
    {
      key: 'purchases',
      header: t('suppliers.totalPurchases'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.total_purchases}</span>,
    },
    {
      key: 'payable',
      header: t('suppliers.payable'),
      align: 'end',
      // ⚠️  A positive balance means **we owe** — emphasised by weight because it is
      //     what the screen is opened for.
      render: (row) => (
        <strong dir="ltr" className={Number(row.payable) > 0 ? 'supplier-owed' : ''}>
          {row.payable}
        </strong>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <div className="supplier-flags">
          {row.is_active ? (
            <Badge tone="success">{t('suppliers.active')}</Badge>
          ) : (
            <Badge tone="neutral">{t('suppliers.inactive')}</Badge>
          )}
          {/* ⚠️  Overdue is its own flag rather than a status: an active supplier with an
              overdue invoice is a common state — and merging them hides one of the two. */}
          {row.has_overdue ? <Badge tone="danger">{t('suppliers.overdue')}</Badge> : null}
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setSelected(row)}>
          {t('suppliers.open')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t('suppliers.title')} />

      {/* ⚠️  "What needs buying" is a tab on the suppliers screen rather than a distant
          one: whoever opens the suppliers opens them in order to buy, and the
          shortage is the reason for opening — not the list of names. */}
      <div className="supplier-view-tabs" role="tablist">
        {(['suppliers', 'reorder'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={view === value}
            className={view === value ? 'is-active' : ''}
            onClick={() => setView(value)}
          >
            {t(`suppliers.view.${value}`)}
          </button>
        ))}
      </div>

      {view === 'reorder' ? <ReorderPanel /> : null}

      {view === 'suppliers' ? (
      <>
      <FilterBar>
        <FilterSearch
          value={search}
          onChange={(value) => {
            setSearch(value);
            reset();
          }}
          placeholder={t('suppliers.searchPlaceholder')}
        />
        <FilterSelect
          label={t('admin.status')}
          value={status}
          onChange={(value) => {
            setStatus(value);
            reset();
          }}
          options={[
            { value: 'active', label: t('suppliers.active') },
            { value: 'inactive', label: t('suppliers.inactive') },
          ]}
        />
      </FilterBar>

      {/* ⚠️  The two follow-up filters are switches rather than a list: they are used
          together often ("has debt **and** is overdue"), and a list permits one. */}
      <div className="supplier-toggles">
        <label>
          <input
            type="checkbox"
            checked={hasDebt}
            onChange={(event) => {
              setHasDebt(event.target.checked);
              reset();
            }}
          />
          {t('suppliers.hasDebt')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={overdue}
            onChange={(event) => {
              setOverdue(event.target.checked);
              reset();
            }}
          />
          {t('suppliers.hasOverdue')}
        </label>
      </div>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('suppliers.noSuppliers')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
      </>
      ) : null}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        {...(selected ? { title: localized(selected, 'name') } : {})}
      >
        {selected ? <SupplierPanel key={selected.id} supplier={selected} /> : null}
      </Drawer>
    </>
  );
}
