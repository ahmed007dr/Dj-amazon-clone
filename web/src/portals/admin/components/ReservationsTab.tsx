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
 * الحجوزات.
 *
 * ⚠️  **هذه الشاشة تجيب سؤالًا واحدًا: «أين الفرق؟»**
 *
 *     «الرصيد ١٠٠ والمتاح ٦٠» يجعل أمين المخزن يظن أن النظام
 *     يُخفي بضاعة أو أن الجرد خاطئ. الأربعون في سلال مفتوحة
 *     وطلبات لم تُشحن — وبلا هذه القائمة لا سبيل لرؤيتها.
 *
 * ⚠️  و**القائمة تبدأ بالنشط**: المنتهي والمستهلَك تاريخ لا يخصم
 *     من المتاح، وعرضه أولًا يُغرق ما يُبحث عنه.
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
      // ⚠️  المرجع هو الجواب: «سلة» أو «طلب رقم كذا» — بدونه
      //     يعرف الأدمن أن هناك حجزًا ولا يعرف كيف يفكّه.
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
