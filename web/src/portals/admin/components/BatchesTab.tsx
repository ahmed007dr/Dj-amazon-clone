import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useBatches, useInventoryLocations, type Batch } from '@/features/inventory/api';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { FilterBar, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { formatDate } from '@/shared/utils/format';

import './BatchesTab.css';

/**
 * Batches.
 *
 * ⚠️  **The batch is what makes FEFO possible** — and the screen is read by expiry.
 *
 *     The warehouse keeper opens it to learn what goes out first and what is
 *     about to be wasted. Ordering it by receipt or by name leaves the question
 *     unanswered.
 *
 * ⚠️  And **the expired are highlighted, not hidden**.
 *
 *     A batch that has expired and is still in the warehouse is the most
 *     dangerous: goods that might be sold. Hiding it behind an "active" filter
 *     makes it vanish from whoever must see it.
 */
export function BatchesTab() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const [location, setLocation] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);

  const locations = useInventoryLocations();
  const query = useBatches({
    ...(location ? { location } : {}),
    ...(status ? { status } : {}),
    page,
  });

  const columns: Column<Batch>[] = [
    {
      key: 'number',
      header: t('inventory.batchNumber'),
      render: (row) => (
        <div className="batch-cell">
          <code dir="ltr">{row.number}</code>
          {row.supplier_batch_number ? (
            <span className="batch-muted" dir="ltr">
              {row.supplier_batch_number}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'product',
      header: t('inventory.product'),
      render: (row) => (
        <div className="batch-cell">
          <span>{row.product_sku}</span>
        </div>
      ),
    },
    {
      key: 'location',
      header: t('inventory.location'),
      secondary: true,
      render: (row) => row.location_code,
    },
    {
      key: 'quantity',
      header: t('inventory.remaining'),
      align: 'end',
      // ⚠️  "40 of 100", not "40": the remainder alone does not say how much was consumed.
      render: (row) => (
        <span dir="ltr">
          {row.quantity_remaining} / {row.quantity_received}
        </span>
      ),
    },
    {
      key: 'cost',
      header: t('inventory.unitCost'),
      align: 'end',
      secondary: true,
      render: (row) => <span dir="ltr">{row.unit_cost}</span>,
    },
    {
      key: 'expiry',
      header: t('inventory.expiresAt'),
      render: (row) =>
        row.expires_at ? (
          <div className="batch-cell">
            <span dir="ltr">{formatDate(row.expires_at, i18n.language)}</span>
            {/* ⚠️  "Expired" as text rather than a negative number: "−12 days" is
                read with hesitation, and "expired" admits no interpretation. */}
            {row.is_expired ? (
              <span className="batch-expired">{t('inventory.expired')}</span>
            ) : row.days_to_expiry !== null && row.days_to_expiry <= 90 ? (
              <span className="batch-soon">
                {t('inventory.daysLeft', { count: row.days_to_expiry })}
              </span>
            ) : null}
          </div>
        ) : (
          // ⚠️  "No expiry" rather than a dash: an item that cannot expire (a device)
          //     is an intended state, not missing data.
          <span className="batch-muted">{t('inventory.noExpiry')}</span>
        ),
    },
    {
      key: 'flags',
      header: '',
      render: (row) =>
        row.is_quarantined ? <Badge tone="danger">{t('inventory.quarantined')}</Badge> : null,
    },
  ];

  return (
    <>
      <FilterBar>
        <FilterSelect
          label={t('inventory.location')}
          value={location}
          onChange={(value) => {
            setLocation(value);
            setPage(1);
          }}
          options={(locations.data ?? []).map((row) => ({
            value: row.id,
            label: localized(row, 'name'),
          }))}
        />
        <FilterSelect
          label={t('admin.status')}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: 'active', label: t('inventory.batchActive') },
            { value: 'expiring', label: t('inventory.batchExpiring') },
            { value: 'expired', label: t('inventory.batchExpired') },
          ]}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('inventory.noBatches')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}
    </>
  );
}
