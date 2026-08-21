import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useApplyCount,
  useCancelCount,
  useInventoryLocations,
  useOpenCount,
  useStockCount,
  useStockCounts,
  type StockCount,
} from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Drawer } from '@/shared/ui/Drawer';
import { Pagination } from '@/shared/ui/Pagination';
import { useToast } from '@/shared/ui/useToast';
import { formatDateTime } from '@/shared/utils/format';

import { CountSheet } from './CountSheet';

import './StockCountsTab.css';

const TONE: Record<string, 'info' | 'warning' | 'success' | 'neutral'> = {
  DRAFT: 'neutral',
  IN_PROGRESS: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'neutral',
};

/**
 * Stock counting.
 *
 * ⚠️  **Opening the session takes the balance snapshot immediately.**
 *
 *     A session with no snapshot stays empty, so the counter assumes it is
 *     ready and starts counting on paper — and the snapshot is taken later
 *     against a balance that has changed.
 *
 * ⚠️  And **one open session per location**, enforced by the server: two
 *     sessions mean two counters, and whoever approves last erases the first
 *     one's work.
 */
export function StockCountsTab() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);
  const [newLocation, setNewLocation] = useState('');

  const locations = useInventoryLocations();
  const query = useStockCounts({ page });
  const detail = useStockCount(openId);

  const open = useOpenCount();
  const apply = useApplyCount();
  const cancel = useCancelCount();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const columns: Column<StockCount>[] = [
    {
      key: 'reference',
      header: t('inventory.countRef'),
      render: (row) => <code dir="ltr">{row.reference}</code>,
    },
    {
      key: 'location',
      header: t('inventory.location'),
      render: (row) => row.location_code,
    },
    {
      key: 'lines',
      header: t('inventory.lines'),
      align: 'end',
      secondary: true,
      render: (row) => row.line_count,
    },
    {
      key: 'variances',
      header: t('inventory.variances'),
      align: 'end',
      // ⚠️  The discrepancy count is what gets read first: a session with zero
      //     discrepancies needs no review, and one with forty needs a pause before approval.
      render: (row) => (
        <strong className={row.variance_count > 0 ? 'count-variance' : ''}>
          {row.variance_count}
        </strong>
      ),
    },
    {
      key: 'started',
      header: t('inventory.startedAt'),
      secondary: true,
      render: (row) =>
        row.started_at ? formatDateTime(row.started_at, i18n.language) : '—',
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (row) => (
        <Badge tone={TONE[row.status] ?? 'neutral'}>
          {t(`inventory.countStatus.${row.status}`)}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'end',
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setOpenId(row.id)}>
          {row.status === 'IN_PROGRESS' ? t('inventory.count') : t('suppliers.open')}
        </Button>
      ),
    },
  ];

  return (
    <>
      <div className="count-start">
        <label>
          {t('inventory.newCount')}
          <select value={newLocation} onChange={(event) => setNewLocation(event.target.value)}>
            <option value="">{t('common.choose')}</option>
            {(locations.data ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {localized(row, 'name')} · {row.code}
              </option>
            ))}
          </select>
        </label>
        <Button
          loading={open.isPending}
          disabled={newLocation === ''}
          onClick={() =>
            open.mutate(
              { location: newLocation },
              {
                onSuccess: (created) => {
                  setNewLocation('');
                  setOpenId(created.id);
                  notify(t('inventory.countOpened', { count: created.lines.length }), 'success');
                },
                onError: fail,
              },
            )
          }
        >
          {t('inventory.startCount')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        isLoading={query.isPending}
        error={query.error}
        rowKey={(row) => row.id}
        emptyTitle={t('inventory.noCounts')}
        emptyBody={t('inventory.noCountsBody')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Drawer
        open={openId !== null}
        onClose={() => setOpenId(null)}
        {...(detail.data ? { title: detail.data.reference } : {})}
      >
        {detail.data ? (
          <div className="count-panel">
            {detail.data.status === 'IN_PROGRESS' ? (
              <Alert tone="info">{t('inventory.countHint')}</Alert>
            ) : null}

            <CountSheet count={detail.data} />

            {detail.data.status === 'IN_PROGRESS' ? (
              <div className="count-panel__actions">
                <Button
                  variant="ghost"
                  onClick={() => {
                    const why = window.prompt(t('inventory.cancelCountReason'));
                    if (!why?.trim()) return;
                    cancel.mutate(
                      { id: detail.data.id, reason: why },
                      { onSuccess: () => setOpenId(null), onError: fail },
                    );
                  }}
                >
                  {t('common.cancel')}
                </Button>
                {/* ⚠️  Approval is irreversible: the discrepancies become recorded
                    movements, and correction goes through a new count, not an undo. */}
                <Button
                  variant="danger"
                  loading={apply.isPending}
                  onClick={() =>
                    apply.mutate(detail.data.id, {
                      onSuccess: (result) => {
                        notify(
                          t('inventory.countApplied', {
                            adjusted: result.adjusted,
                            surplus: result.surplus,
                            shortage: result.shortage,
                          }),
                          'success',
                        );
                        setOpenId(null);
                      },
                      onError: fail,
                    })
                  }
                >
                  {t('inventory.applyCount')}
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </>
  );
}
