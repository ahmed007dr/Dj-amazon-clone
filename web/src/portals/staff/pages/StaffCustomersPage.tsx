import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMyCustomers, type AssignedCustomer } from '@/features/employees/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { formatDate } from '@/shared/utils/format';

import { CustomerPanel } from '../components/CustomerPanel';

import './StaffCustomersPage.css';

/**
 * عملاء المندوب.
 *
 * ⚠️  **البحث يعمل داخل المُسنَد — والخادم هو من يضمن ذلك.**
 *
 *     التصفية هنا تحسين تجربة لا أمان: `/employees/customers/`
 *     مُصفّاة بالإسناد على الخادم، ولا تعيد عميل زميل مهما كان
 *     نص البحث.
 */
export function StaffCustomersPage() {
  const { t, i18n } = useTranslation();

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AssignedCustomer | null>(null);

  const debounced = useDebounced(search);
  const query = useMyCustomers(debounced, page);

  const columns: Column<AssignedCustomer>[] = [
    {
      key: 'name',
      header: t('staff.customer'),
      render: (row) => (
        <div className="staff-customer-cell">
          <strong>{row.display_name}</strong>
          <code>{row.customer_number}</code>
        </div>
      ),
    },
    {
      key: 'phone',
      header: t('staff.phone'),
      secondary: true,
      render: (row) => <span dir="ltr">{row.phone || '—'}</span>,
    },
    {
      key: 'segment',
      header: t('staff.segment'),
      secondary: true,
      render: (row) => <Badge tone="neutral">{row.segment}</Badge>,
    },
    {
      key: 'orders',
      header: t('staff.ordersCount'),
      align: 'end',
      render: (row) => row.total_orders,
    },
    {
      key: 'spent',
      header: t('staff.totalSpent'),
      align: 'end',
      render: (row) => <span dir="ltr">{row.total_spent}</span>,
    },
    {
      key: 'last',
      header: t('staff.lastOrder'),
      secondary: true,
      // ⚠️  «لم يطلب بعد» لا شرطة: العميل الذي لم يشترِ قط هو
      //     بالضبط من يجب أن يتصل به المندوب، وشرطة تخفيه.
      render: (row) =>
        row.last_order_at ? (
          formatDate(row.last_order_at, i18n.language)
        ) : (
          <span className="staff-never">{t('staff.neverOrdered')}</span>
        ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setSelected(row)}>
          {t('staff.open')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t('staff.myCustomers')} />

      <FilterBar>
        <FilterSearch
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          placeholder={t('staff.searchPlaceholder')}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('staff.noCustomers')}
        emptyBody={t('staff.noCustomersBody')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        {...(selected ? { title: selected.display_name } : {})}
      >
        {selected ? <CustomerPanel key={selected.id} customer={selected} /> : null}
      </Drawer>
    </>
  );
}
