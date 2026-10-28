import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAdminOrders } from '@/features/orders/adminHooks';
import type { AdminOrder } from '@/features/orders/adminApi';
import {
  OrderStatusBadge,
  PaymentStatusBadge,
} from '@/features/orders/components/OrderStatusBadge';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { formatDate, formatMoney } from '@/shared/utils/format';

const STATUSES = [
  '',
  'PENDING',
  'CONFIRMED',
  'PROCESSING',
  'SHIPPED',
  'DELIVERED',
  'COMPLETED',
  'CANCELLED',
];

/**
 * Admin orders.
 *
 * ⚠️  The default tab is **"pending", not "all"**.
 *
 *     Whoever opens this screen opens it to process orders waiting on them; and
 *     an "all" list buries the ten new ones under a thousand old.
 */
export function AdminOrdersPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const [status, setStatus] = useState('PENDING');
  const [search, setSearch] = useState('');
  // ⚠️  "Guest orders" is the list the owner works from by phone — it is a filter
  //     on the server, not a client-side cut of whatever page happens to be loaded.
  const [buyer, setBuyer] = useState('');
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebounced(search);

  const query = useAdminOrders({
    ...(status ? { status } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(buyer ? { guest: buyer } : {}),
    page,
  });

  const columns: Column<AdminOrder>[] = [
    {
      key: 'number',
      header: t('admin.orderNumber'),
      render: (order) => <strong style={{ direction: 'ltr' }}>{order.number}</strong>,
    },
    {
      key: 'customer',
      header: t('admin.customer'),
      render: (order) =>
        order.is_guest ? (
          // A guest has no account: the badge says so, and the name + phone are
          // what the person confirming the order by phone actually needs.
          <span style={{ display: 'inline-grid', gap: '0.15rem' }}>
            <span>
              <Badge tone="info">{t('guest.badge')}</Badge> {order.recipient_name}
            </span>
            <span className="muted" style={{ direction: 'ltr' }}>
              {order.recipient_phone}
            </span>
          </span>
        ) : (
          <span className="truncate" style={{ direction: 'ltr', display: 'inline-block' }}>
            {order.customer_email}
          </span>
        ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (order) => <OrderStatusBadge status={order.status} />,
    },
    {
      key: 'payment',
      header: t('admin.payment'),
      render: (order) => <PaymentStatusBadge status={order.payment_status} />,
    },
    {
      key: 'total',
      header: t('cart.total'),
      align: 'end',
      render: (order) => formatMoney(order.grand_total, i18n.language),
    },
    {
      key: 'created',
      header: t('admin.createdAt'),
      render: (order) => formatDate(order.created_at, i18n.language),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('nav.orders')}
        {...(query.data ? { description: t('admin.total', { count: query.data.count }) } : {})}
      />

      <StatusTabs
        options={STATUSES.map((value) => ({
          value,
          label: value ? t(`orderStatus.${value}`) : t('common.all'),
        }))}
        value={status}
        onChange={(next) => {
          setStatus(next);
          // ⚠️  Returning to the first page when the filter changes: staying on
          //     page 7 in a two-page result shows an empty list.
          setPage(1);
        }}
      />

      <FilterBar
        hasFilters={Boolean(search) || Boolean(buyer)}
        onClear={() => {
          setSearch('');
          setBuyer('');
          setPage(1);
        }}
      >
        <FilterSearch
          value={search}
          onChange={(next) => {
            setSearch(next);
            setPage(1);
          }}
          placeholder={t('admin.searchOrders')}
        />
        <FilterSelect
          value={buyer}
          onChange={(next) => {
            setBuyer(next);
            setPage(1);
          }}
          label={t('guest.filterLabel')}
          options={[
            { value: 'true', label: t('guest.filterGuests') },
            { value: 'false', label: t('guest.filterMembers') },
          ]}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(order) => order.id}
        isLoading={query.isPending}
        error={query.error}
        onRowClick={(order) => void navigate(`/admin/orders/${order.id}`)}
        emptyTitle={t('admin.noOrders')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
