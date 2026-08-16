import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSuppliers, type Supplier } from '@/features/suppliers/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
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
 * الموردون.
 *
 * ⚠️  **الرصيد وإجمالي المشتريات في القائمة نفسها.**
 *
 *     من يفتح هذه الشاشة يفتحها ليعرف «كم علينا لمن؟» قبل أي شيء.
 *     دفنهما في التفاصيل يجبره على فتح كل مورّد ليجد من يستحق
 *     السداد — وهو ما تُفتح الشاشة لأجله.
 *
 * ⚠️  والرقمان يأتيان من **تجميع في استعلام واحد** لا من نداء لكل
 *     صف: الحساب لكل مورّد على حدة كان استعلامًا لكل سطر.
 */
export function AdminSuppliersPage() {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [hasDebt, setHasDebt] = useState(false);
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
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
      // ⚠️  الرصيد الموجب يعني **علينا** — يُبرَز بالوزن لأنه ما
      //     تُفتح الشاشة لأجله.
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
          {/* ⚠️  المتأخر علامة مستقلة لا حالة: مورّد نشط وله فاتورة
              متأخرة حالة شائعة — ودمجهما يُخفي إحداهما. */}
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

      {/* ⚠️  فلترا المتابعة مفتاحان لا قائمة: يُستخدمان معًا كثيرًا
          («عليه مديونية **و**متأخر»)، والقائمة تسمح بواحد. */}
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
