import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useReservations, type StockReservation } from '@/features/inventory/api';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';

import './ReservationsTab.css';

const TONE: Record<string, 'info' | 'success' | 'neutral' | 'danger'> = {
  ACTIVE: 'info',
  CONSUMED: 'success',
  RELEASED: 'neutral',
  EXPIRED: 'danger',
};

/**
 * Reservations.
 *
 * ⚠️  **This screen answers one question: "where is the difference?"**
 *
 *     "The balance is 100 and available is 60" makes the warehouse keeper think
 *     the system is hiding goods or the stock count is wrong. The forty are in
 *     open carts and unshipped orders — and without this list there is no way
 *     to see them.
 *
 * ⚠️  And **the list starts with the active ones**: the expired and the
 *     fulfilled are history that is not deducted from available, and showing
 *     them first drowns what is being looked for.
 */
export function ReservationsTab() {
  const { t } = useTranslation();

  const [status, setStatus] = useState('ACTIVE');
  const [page, setPage] = useState(1);

  const query = useReservations({ ...(status ? { status } : {}), page });

  const columns: Column<StockReservation>[] = [
    {
      key: 'product',
      header: t('suppliers.product'),
      render: (row) => <code dir="ltr">{row.product_sku}</code>,
    },
    {
      key: 'quantity',
      header: t('admin.reserved'),
      align: 'end',
      render: (row) => <strong dir="ltr">{row.quantity}</strong>,
    },
    {
      key: 'reference',
      header: t('inventory.heldBy'),
      // ⚠️  The reference is the answer: "a cart" or "order number such-and-such" —
      //     without it the admin knows there is a reservation and not how to release it.
      render: (row) => (
        <div className="reservation-ref">
          <span>
            {t(`inventory.refType.${row.reference_type}`, { defaultValue: row.reference_type })}
          </span>
          <code dir="ltr">{row.reference_id}</code>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONE[row.status] ?? 'neutral'}>
          {t(`inventory.reservationStatus.${row.status}`, { defaultValue: row.status })}
        </Badge>
      ),
    },
    {
      key: 'expires',
      header: t('inventory.expiresAt'),
      secondary: true,
      render: (row) => <span dir="ltr">{row.expires_at?.slice(0, 16).replace('T', ' ') ?? '—'}</span>,
    },
  ];

  return (
    <>
      <StatusTabs
        options={[
          { value: 'ACTIVE', label: t('inventory.reservationStatus.ACTIVE') },
          { value: 'CONSUMED', label: t('inventory.reservationStatus.CONSUMED') },
          { value: 'RELEASED', label: t('inventory.reservationStatus.RELEASED') },
          { value: 'EXPIRED', label: t('inventory.reservationStatus.EXPIRED') },
        ]}
        value={status}
        onChange={(next) => {
          setStatus(next);
          setPage(1);
        }}
      />

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(row) => row.id}
        isLoading={query.isPending}
        error={query.error}
        emptyTitle={t('inventory.noReservations')}
        emptyBody={t('inventory.noReservationsBody')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
