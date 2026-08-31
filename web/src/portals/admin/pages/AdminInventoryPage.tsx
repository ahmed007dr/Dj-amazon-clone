import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  listAlerts,
  listLocations,
  listMovements,
  listStock,
  listUnstocked,
  runMaintenance,
  useUpdateStockThresholds,
  type Stock,
  type StockAlert,
  type StockMovement,
  type UnstockedProduct,
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
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { FilterBar, FilterSearch, FilterSelect } from '@/shared/ui/FilterBar';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { ExportButton } from '@/portals/admin/components/ExportButton';
import { ReservationsTab } from '@/portals/admin/components/ReservationsTab';
import { useToast } from '@/shared/ui/useToast';
import { formatDate, formatDateTime, formatMoney } from '@/shared/utils/format';

import './AdminInventoryPage.css';

/**
 * ⚠️  The movement type carries **its direction**, not just its name.
 *
 *     Inbound, outbound and loss are three entirely different meanings to the
 *     warehouse keeper, and reading them from one colour makes a damage line
 *     look like a receipt line.
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
 * ⚠️  The tabs are ordered by what gets opened first, not by build order.
 *
 *     The warehouse keeper opens the screen on the alerts: what has run out and
 *     what is close to expiring. The stock count, by contrast, is opened once a
 *     month — and its place is last.
 */
type Tab =
  | 'alerts'
  | 'stock'
  | 'unstocked'
  | 'batches'
  | 'movements'
  | 'counts'
  | 'reservations';

/**
 * Which tabs offer an inline export.
 *
 * ⚠️  `movements` is deliberately absent, and so are `counts` and `reservations`.
 *
 *     The movements dataset requires a period — the table grows without bound —
 *     and this screen has no date pickers. A button here would either fail with
 *     "choose a period", or invent one and hand back a file covering a different
 *     range from the one on screen, which the `_meta` sheet would faithfully
 *     record and nobody would read. Movements are exported from `/admin/exports`,
 *     where the dates exist. Counts and reservations have no dataset at all.
 */
const EXPORTABLE_TABS: Partial<Record<Tab, string>> = {
  alerts: 'stock-alerts',
  stock: 'stock-levels',
  batches: 'batches',
};

const ALERT_TONES = {
  LOW_STOCK: 'warning',
  CRITICAL_STOCK: 'danger',
  OUT_OF_STOCK: 'danger',
  EXPIRING_SOON: 'warning',
  EXPIRED: 'danger',
} as const;

/**
 * Inventory.
 *
 * ⚠️  The default tab is **the alerts, not the balances**.
 *
 *     The full balances list does not get read — a thousand rows with no
 *     priority. The alerts, by contrast, are exactly what needs acting on
 *     today: out of stock · critical · about to expire.
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
  // ⚠️  Off by default: "never received" and "received then sold out" are
  //     different problems, and merging them hides which is which.
  const [includeZero, setIncludeZero] = useState(false);
  const [movementType, setMovementType] = useState('');
  const [page, setPage] = useState(1);

  // The open panel — which operation is being performed right now
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

  // ⚠️  The products with no stock row at all — the balances list cannot show them.
  //
  //     It pages over `Stock` rows and these have none, so they fall outside its
  //     search and its `status=out` filter alike. Since the storefront hides
  //     whatever has zero available, this is the only screen that can explain why
  //     a product is missing from the shop.
  const unstocked = useQuery({
    queryKey: ['inventory', 'unstocked', debouncedSearch, includeZero, page],
    queryFn: () =>
      listUnstocked({
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(includeZero ? { include_zero: 'true' } : {}),
        page,
      }),
    enabled: tab === 'unstocked',
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
    // ⚠️  The log is append-only — what has been read does not change, and repeated
    //     refetching serves no purpose. Only the first page grows, and the
    //     invalidation after every movement takes care of it.
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

  const unstockedColumns: Column<UnstockedProduct>[] = [
    {
      key: 'product',
      header: t('catalog.product'),
      render: (row) => (
        <span>
          <code style={{ direction: 'ltr' }}>{row.sku}</code> — {localized(row, 'name')}
        </span>
      ),
    },
    {
      key: 'price',
      header: t('catalog.price'),
      align: 'end',
      render: (row) => formatMoney(row.base_price, i18n.language),
    },
    {
      key: 'action',
      header: '',
      align: 'end',
      // ⚠️  The remedy sits on the row. Seeing the list and then hunting for the
      //     product again in the receive form is the same search done twice.
      render: () => (
        <Button size="sm" variant="ghost" onClick={() => setAction('receive')}>
          {t('inventory.action_receive')}
        </Button>
      ),
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
      // ⚠️  **The thresholds are edited in place — and the quantities are not.**
      //
      //     The reorder point is a number tuned by experiment season after season,
      //     and burying it behind an edit screen makes it stay on its first
      //     value forever, so the alerts become noise that gets ignored. The
      //     quantities, by contrast, have their recorded paths (receipt · adjustment ·
      //     transfer), and the server refuses to edit them from here at all.
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
      // ⚠️  The sign is displayed as it is: `−50` reads as an outflow immediately, and `50`
      //     bare needs the type column read to be understood.
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
      // ⚠️  An automatic movement has no operator — "the system" rather than blank,
      //     or the field looks missing rather than deliberate.
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
            {EXPORTABLE_TABS[tab] ? (
              <ExportButton
                dataset={EXPORTABLE_TABS[tab]}
                params={{ ...(location ? { location } : {}) }}
              />
            ) : null}
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
          // ⚠️  Beside the balances, because it is the question the balances
          //     cannot answer — not a filter inside them.
          { value: 'unstocked', label: t('inventory.unstocked') },
          { value: 'batches', label: t('inventory.batches') },
          { value: 'movements', label: t('inventory.movements') },
          { value: 'counts', label: t('inventory.counts') },
          // ⚠️  Reservations beside the balances: they are the explanation of the gap
          //     between the balance and available, and whoever opens the balances is who asks about it.
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

      {tab === 'unstocked' ? (
        <FilterBar
          hasFilters={Boolean(search || includeZero)}
          onClear={() => {
            setSearch('');
            setIncludeZero(false);
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
            value={includeZero ? 'all' : 'never'}
            label={t('inventory.unstockedScope')}
            options={[
              { value: 'never', label: t('inventory.neverReceived') },
              { value: 'all', label: t('inventory.allUnsellable') },
            ]}
            onChange={(next) => {
              setIncludeZero(next === 'all');
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
        // ⚠️  A separate component rather than a branch here: the tab has its own
        //     filters and its own pagination, and cramming them into the page's
        //     state makes changing the batches filter reset the movements page.
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
      ) : tab === 'unstocked' ? (
        <>
          {/* ⚠️  The count is the point of this screen — it is the size of the
              gap between the catalogue and what a customer can actually buy. */}
          {unstocked.data ? (
            <Alert tone={unstocked.data.count > 0 ? 'warning' : 'success'}>
              {unstocked.data.count > 0
                ? t('inventory.unstockedCount', { count: unstocked.data.count })
                : t('inventory.allStocked')}
            </Alert>
          ) : null}

          <DataTable
            columns={unstockedColumns}
            rows={unstocked.data?.results ?? []}
            rowKey={(row) => row.id}
            isLoading={unstocked.isPending}
            error={unstocked.error}
            emptyTitle={t('inventory.allStocked')}
            emptyBody={t('inventory.allStockedBody')}
          />
          {unstocked.data ? (
            <Pagination
              page={unstocked.data.page}
              pages={unstocked.data.pages}
              onChange={setPage}
            />
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
        {/* ⚠️  The panel is mounted only on opening, and its key is the operation type.
            Leaving it mounted made "adjustment" open with a quantity and a
            reason the admin had typed into "damage" moments earlier. */}
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
