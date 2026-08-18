import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listAlerts,
  listLocations,
  listMovements,
  listStock,
  runMaintenance,
  useUpdateStockThresholds,
  type Stock,
  type StockAlert,
  type StockMovement,
} from '@/features/inventory/api';
import { BatchesTab } from '@/portals/admin/components/BatchesTab';
import { StockCountsTab } from '@/portals/admin/components/StockCountsTab';
import {
  StockMovementForm,
  type MovementAction,
} from '@/portals/admin/components/StockMovementForm';
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
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { ReservationsTab } from '@/portals/admin/components/ReservationsTab';
import { useToast } from '@/shared/ui/useToast';
import { formatDate, formatDateTime } from '@/shared/utils/format';

import './AdminInventoryPage.css';

/**
 * ⚠️  نوع الحركة يحمل **اتجاهها** لا اسمها وحده.
 *
 *     الوارد والصادر والفاقد ثلاثة معانٍ مختلفة تمامًا لأمين
 *     المخزن، وقراءتها من لون واحد تجعل سطر تلف يبدو كسطر استلام.
 */
const MOVEMENT_TONES: Record<string, 'success' | 'neutral' | 'warning' | 'danger'> = {
  RECEIPT: 'success',
  RETURN_IN: 'success',
  TRANSFER_IN: 'success',
  ADJUSTMENT_UP: 'success',
  SALE: 'neutral',
  RETURN_OUT: 'neutral',
  TRANSFER_OUT: 'neutral',
  ADJUSTMENT_DOWN: 'warning',
  COUNT: 'warning',
  RESERVE: 'neutral',
  RELEASE: 'neutral',
  DAMAGE: 'danger',
  EXPIRY: 'danger',
};

const MOVEMENT_ACTIONS: MovementAction[] = ['receive', 'adjust', 'transfer', 'damage'];

/**
 * ⚠️  التبويبات مرتّبة بما يُفتح أولًا لا بترتيب البناء.
 *
 *     أمين المخزن يفتح الشاشة على التنبيهات: ما نفد وما قارب
 *     الانتهاء. أما الجرد فيُفتح مرة كل شهر — وموضعه في الآخر.
 */
type Tab = 'alerts' | 'stock' | 'batches' | 'movements' | 'counts' | 'reservations';

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

  const thresholds = useUpdateStockThresholds();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const [tab, setTab] = useState<Tab>('alerts');
  const [search, setSearch] = useState('');
  const [location, setLocation] = useState('');
  const [status, setStatus] = useState('');
  const [movementType, setMovementType] = useState('');
  const [page, setPage] = useState(1);

  // اللوح المفتوح — أي عملية يجري تنفيذها الآن
  const [action, setAction] = useState<MovementAction | null>(null);

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

  const movements = useQuery({
    queryKey: ['inventory', 'movements', location, movementType, page],
    queryFn: () =>
      listMovements({
        ...(location ? { location } : {}),
        ...(movementType ? { type: movementType } : {}),
        page,
      }),
    enabled: tab === 'movements',
    // ⚠️  السجل إضافة فقط — ما قُرئ لا يتغيّر، وإعادة الجلب المتكررة
    //     بلا فائدة. الصفحة الأولى وحدها تنمو، والإبطال بعد كل حركة
    //     يتكفّل بها.
    staleTime: 60 * 1000,
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
    {
      key: 'thresholds',
      header: t('inventory.thresholds'),
      align: 'end',
      // ⚠️  **الحدود تُعدَّل في مكانها — والكميات لا.**
      //
      //     نقطة إعادة الطلب رقم يُضبط بالتجربة موسمًا بعد موسم،
      //     ودفنه خلف شاشة تعديل يجعله يبقى على قيمته الأولى
      //     للأبد فتصير التنبيهات ضجيجًا يُتجاهَل. أما الكميات
      //     فلها مساراتها المسجَّلة (استلام · تسوية · تحويل)،
      //     والخادم يرفض تعديلها من هنا أصلًا.
      render: (row) => (
        <span className="stock-thresholds">
          <input
            type="number"
            min="0"
            dir="ltr"
            aria-label={t('inventory.reorderPoint')}
            defaultValue={row.reorder_point}
            onBlur={(event) => {
              const value = Number(event.target.value);
              if (value < 0 || value === row.reorder_point) return;
              thresholds.mutate(
                { id: row.id, reorder_point: value },
                {
                  onSuccess: () => notify(t('inventory.thresholdSaved'), 'success'),
                  onError: fail,
                },
              );
            }}
          />
          <input
            type="number"
            min="0"
            dir="ltr"
            aria-label={t('inventory.criticalPoint')}
            defaultValue={row.critical_point}
            onBlur={(event) => {
              const value = Number(event.target.value);
              if (value < 0 || value === row.critical_point) return;
              thresholds.mutate(
                { id: row.id, critical_point: value },
                {
                  onSuccess: () => notify(t('inventory.thresholdSaved'), 'success'),
                  onError: fail,
                },
              );
            }}
          />
        </span>
      ),
    },
  ];

  const movementColumns: Column<StockMovement>[] = [
    {
      key: 'created',
      header: t('admin.createdAt'),
      render: (row) => formatDateTime(row.created_at, i18n.language),
    },
    {
      key: 'type',
      header: t('inventory.movementType'),
      render: (row) => (
        <Badge tone={MOVEMENT_TONES[row.movement_type] ?? 'neutral'}>
          {t(`movementType.${row.movement_type}`)}
        </Badge>
      ),
    },
    {
      key: 'product',
      header: t('catalog.product'),
      render: (row) => <code style={{ direction: 'ltr' }}>{row.product_sku}</code>,
    },
    {
      key: 'location',
      header: t('admin.location'),
      secondary: true,
      render: (row) => row.location_code,
    },
    {
      key: 'quantity',
      header: t('inventory.quantity'),
      align: 'end',
      // ⚠️  الإشارة تُعرض كما هي: `−٥٠` تُقرأ خروجًا فورًا، و`٥٠`
      //     المجرّدة تحتاج قراءة عمود النوع لفهمها.
      render: (row) => (
        <strong className={row.quantity < 0 ? 'inventory-out' : 'inventory-in'}>
          {row.quantity > 0 ? `+${row.quantity}` : row.quantity}
        </strong>
      ),
    },
    {
      key: 'balance',
      header: t('inventory.balanceAfter'),
      align: 'end',
      secondary: true,
      render: (row) => row.balance_after,
    },
    {
      key: 'by',
      header: t('inventory.performedBy'),
      secondary: true,
      // ⚠️  الحركة الآلية بلا منفّذ — «النظام» لا فراغ، وإلا بدا
      //     الحقل ناقصًا لا مقصودًا.
      render: (row) => row.performed_by_email ?? t('inventory.systemActor'),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('nav.inventory')}
        actions={
          <div className="inventory-actions">
            {MOVEMENT_ACTIONS.map((item) => (
              <Button
                key={item}
                size="sm"
                variant={item === 'receive' ? 'primary' : 'secondary'}
                onClick={() => setAction(item)}
              >
                {t(`inventory.action_${item}`)}
              </Button>
            ))}
            <Button
              size="sm"
              variant="ghost"
              loading={maintenance.isPending}
              onClick={() => {
                maintenance.mutate();
              }}
            >
              {t('admin.runMaintenance')}
            </Button>
          </div>
        }
      />

      <StatusTabs
        options={[
          { value: 'alerts', label: t('admin.alerts'), ...(alerts.data ? { count: alerts.data.count } : {}) },
          { value: 'stock', label: t('admin.stockLevels') },
          { value: 'batches', label: t('inventory.batches') },
          { value: 'movements', label: t('inventory.movements') },
          { value: 'counts', label: t('inventory.counts') },
          // ⚠️  الحجوزات بجوار الأرصدة: هي تفسير الفرق بين الرصيد
          //     والمتاح، ومن يفتح الأرصدة هو من يسأل عنه.
          { value: 'reservations', label: t('inventory.reservations') },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next as Tab);
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

      {tab === 'movements' ? (
        <FilterBar
          hasFilters={Boolean(location || movementType)}
          onClear={() => {
            setLocation('');
            setMovementType('');
            setPage(1);
          }}
        >
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
            value={movementType}
            label={t('inventory.movementType')}
            options={Object.keys(MOVEMENT_TONES).map((value) => ({
              value,
              label: t(`movementType.${value}`),
            }))}
            onChange={(next) => {
              setMovementType(next);
              setPage(1);
            }}
          />
        </FilterBar>
      ) : null}

      {tab === 'movements' ? (
        <>
          <DataTable
            columns={movementColumns}
            rows={movements.data?.results ?? []}
            rowKey={(row) => String(row.id)}
            isLoading={movements.isPending}
            error={movements.error}
            emptyTitle={t('inventory.noMovements')}
            emptyBody={t('inventory.noMovementsBody')}
          />
          {movements.data ? (
            <Pagination
              page={movements.data.page}
              pages={movements.data.pages}
              onChange={setPage}
            />
          ) : null}
        </>
      ) : tab === 'batches' ? (
        // ⚠️  مكوّن مستقل لا فرع هنا: التبويب له فلاتره وترقيمه
        //     الخاصان، وحشرهما في حالة الصفحة يجعل تغيير فلتر
        //     الدفعات يُصفّر صفحة الحركات.
        <BatchesTab />
      ) : tab === 'counts' ? (
        <StockCountsTab />
      ) : tab === 'reservations' ? (
        <ReservationsTab />
      ) : tab === 'alerts' ? (
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

      <Drawer
        open={action !== null}
        onClose={() => setAction(null)}
        {...(action ? { title: t(`inventory.action_${action}`) } : {})}
      >
        {/* ⚠️  اللوح يُركَّب عند الفتح فقط ومفتاحه نوع العملية.
            إبقاؤه مركّبًا كان يجعل «تسوية» تفتح بكمية وسبب كتبهما
            الأدمن في «تلف» قبل قليل. */}
        {action ? (
          <StockMovementForm
            key={action}
            action={action}
            locations={locations.data ?? []}
            onDone={() => setAction(null)}
          />
        ) : null}
      </Drawer>
    </>
  );
}
