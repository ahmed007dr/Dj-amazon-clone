import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listAlerts,
  listLocations,
  listStock,
  runMaintenance,
  type Stock,
  type StockAlert,
} from '@/features/inventory/api';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

const ALERT_TONES = {
  LOW_STOCK: 'warning',
  CRITICAL_STOCK: 'danger',
  OUT_OF_STOCK: 'danger',
  EXPIRING_SOON: 'warning',
  EXPIRED: 'danger',
} as const;

/**
 * المخزون.
 *
 * ⚠️  التبويب الافتراضي **التنبيهات لا الأرصدة**.
 *
 *     قائمة الأرصدة الكاملة لا تُقرأ — ألف صف بلا أولوية. أما
 *     التنبيهات فهي بالضبط ما يحتاج تصرّفًا اليوم: نافد · حرج ·
 *     يوشك على انتهاء الصلاحية.
 */
export function AdminInventoryPage() {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [tab, setTab] = useState<'alerts' | 'stock'>('alerts');
  const [search, setSearch] = useState('');
  const [location, setLocation] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);

  const debouncedSearch = useDebounced(search);

  const locations = useQuery({
    queryKey: ['inventory', 'locations'],
    queryFn: listLocations,
    staleTime: 30 * 60 * 1000,
  });

  const alerts = useQuery({
    queryKey: ['inventory', 'alerts', page],
    queryFn: () => listAlerts({ page }),
    enabled: tab === 'alerts',
    staleTime: 30 * 1000,
  });

  const stock = useQuery({
    queryKey: ['inventory', 'stock', debouncedSearch, location, status, page],
    queryFn: () =>
      listStock({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(location ? { location } : {}),
        ...(status ? { status } : {}),
        page,
      }),
    enabled: tab === 'stock',
    staleTime: 30 * 1000,
  });

  const maintenance = useMutation({
    mutationFn: runMaintenance,
    onSuccess: (result) => {
      notify(
        t('admin.maintenanceDone', {
          released: result.released_reservations ?? 0,
          quarantined: result.quarantined_batches ?? 0,
        }),
      );
      void queryClient.invalidateQueries({ queryKey: ['inventory'] });
    },
  });

  const alertColumns: Column<StockAlert>[] = [
    {
      key: 'type',
      header: t('admin.alertType'),
      render: (alert) => (
        <Badge tone={ALERT_TONES[alert.alert_type]}>{t(`alertType.${alert.alert_type}`)}</Badge>
      ),
    },
    {
      key: 'product',
      header: t('catalog.product'),
      render: (alert) => (
        <span>
          <code style={{ direction: 'ltr' }}>{alert.product_sku}</code> — {alert.product_name}
        </span>
      ),
    },
    {
      key: 'location',
      header: t('admin.location'),
      render: (alert) => alert.location_code,
    },
    {
      key: 'value',
      header: t('admin.current'),
      align: 'end',
      render: (alert) => `${alert.current_value} / ${alert.threshold_value}`,
    },
    {
      key: 'created',
      header: t('admin.createdAt'),
      render: (alert) => formatDate(alert.created_at, i18n.language),
    },
  ];

  const stockColumns: Column<Stock>[] = [
    {
      key: 'product',
      header: t('catalog.product'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.product_sku}</code> — {row.product_name}
        </span>
      ),
    },
    { key: 'location', header: t('admin.location'), render: (row) => row.location_code },
    {
      key: 'physical',
      header: t('admin.physical'),
      align: 'end',
      render: (row) => row.quantity_physical,
    },
    {
      key: 'reserved',
      header: t('admin.reserved'),
      align: 'end',
      render: (row) => row.quantity_reserved,
    },
    {
      key: 'available',
      header: t('admin.available'),
      align: 'end',
      render: (row) => (
        <strong
          style={{
            color: row.is_critical
              ? 'var(--color-danger)'
              : row.needs_reorder
                ? 'var(--color-warning)'
                : undefined,
          }}
        >
          {row.available}
        </strong>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('nav.inventory')}
        actions={
          <Button
            variant="secondary"
            loading={maintenance.isPending}
            onClick={() => {
              maintenance.mutate();
            }}
          >
            {t('admin.runMaintenance')}
          </Button>
        }
      />

      <StatusTabs
        options={[
          { value: 'alerts', label: t('admin.alerts'), ...(alerts.data ? { count: alerts.data.count } : {}) },
          { value: 'stock', label: t('admin.stockLevels') },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next as 'alerts' | 'stock');
          setPage(1);
        }}
      />

      {tab === 'stock' ? (
        <FilterBar
          hasFilters={Boolean(search || location || status)}
          onClear={() => {
            setSearch('');
            setLocation('');
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
            placeholder={t('admin.searchBySku')}
          />

          <FilterSelect
            value={location}
            label={t('admin.location')}
            options={(locations.data ?? []).map((item) => ({
              value: item.id,
              label: localized(item, 'name'),
            }))}
            onChange={(next) => {
              setLocation(next);
              setPage(1);
            }}
          />

          <FilterSelect
            value={status}
            label={t('admin.stockStatus')}
            options={[
              { value: 'out', label: t('catalog.outOfStock') },
              { value: 'critical', label: t('admin.critical') },
              { value: 'low', label: t('catalog.lowStock') },
            ]}
            onChange={(next) => {
              setStatus(next);
              setPage(1);
            }}
          />
        </FilterBar>
      ) : null}

      {tab === 'alerts' ? (
        <>
          <DataTable
            columns={alertColumns}
            rows={alerts.data?.results ?? []}
            rowKey={(alert) => alert.id}
            isLoading={alerts.isPending}
            error={alerts.error}
            emptyTitle={t('admin.noAlerts')}
            emptyBody={t('admin.noAlertsBody')}
          />
          {alerts.data ? (
            <Pagination page={alerts.data.page} pages={alerts.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : (
        <>
          <DataTable
            columns={stockColumns}
            rows={stock.data?.results ?? []}
            rowKey={(row) => String(row.id)}
            isLoading={stock.isPending}
            error={stock.error}
          />
          {stock.data ? (
            <Pagination page={stock.data.page} pages={stock.data.pages} onChange={setPage} />
          ) : null}
        </>
      )}
    </>
  );
}
