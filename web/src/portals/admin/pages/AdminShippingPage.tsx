import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  AdminShippingMethod,
  ShippingRate,
  ShippingZone,
} from '@/features/shipping/api';
import {
  useAdminShippingMethods,
  useDeleteMethod,
  useDeleteRate,
  useDeleteZone,
  useSaveZone,
  useShippingCoverage,
  useShippingRates,
  useShippingZones,
} from '@/features/shipping/hooks';
import { ShippingMethodForm } from '@/portals/admin/components/ShippingMethodForm';
import { ShippingRateForm } from '@/portals/admin/components/ShippingRateForm';
import { ShippingZoneForm } from '@/portals/admin/components/ShippingZoneForm';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Drawer } from '@/shared/ui/Drawer';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatMoney } from '@/shared/utils/format';

import './AdminShippingPage.css';

type Tab = 'zones' | 'methods' | 'rates';

/**
 * Configuring shipping — zones, methods and the fee table.
 *
 * ⚠️  **Separate from `/admin/shipments`, and deliberately.**
 *
 *     That screen moves parcels through the day; this one sets what a delivery
 *     costs. Merging them puts a price field beside a status button on the
 *     busiest screen in the panel — and the fee gets changed while somebody is
 *     trying to mark a shipment delivered.
 *
 * ⚠️  Both sit behind the same permission (`shipping.change_shipment`).
 *
 *     Splitting "configure" from "operate" reads tidier and is wrong in
 *     practice: the person who watches deliveries fail in Upper Egypt is the
 *     person who needs to raise its fee. A second permission means they file a
 *     request instead, and the fee stays wrong until somebody else gets to it.
 *
 * ⚠️  The three tabs are **one chain, in order**: a method with no zone prices
 *     nothing, and a zone with no rate quotes nothing. The tab order is the
 *     order the setup actually has to happen in.
 */
export function AdminShippingPage() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [tab, setTab] = useState<Tab>('zones');

  const [editingZone, setEditingZone] = useState<ShippingZone | null>(null);
  const [editingMethod, setEditingMethod] = useState<AdminShippingMethod | null>(null);
  const [editingRate, setEditingRate] = useState<ShippingRate | null>(null);
  const [creating, setCreating] = useState(false);

  const coverage = useShippingCoverage();
  const zones = useShippingZones();
  const methods = useAdminShippingMethods(tab === 'methods' || tab === 'rates');
  const rates = useShippingRates(tab === 'rates');

  const saveZone = useSaveZone();
  const removeZone = useDeleteZone();
  const removeMethod = useDeleteMethod();
  const removeRate = useDeleteRate();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const deleted = { onSuccess: () => notify(t('shipping.deleted'), 'success'), onError: fail };

  const closeDrawer = () => {
    setCreating(false);
    setEditingZone(null);
    setEditingMethod(null);
    setEditingRate(null);
  };

  /**
   * ⚠️  Promoting a default from the row, not only from the form.
   *
   *     Moving the default is a one-field decision made while looking at the
   *     list of zones. Sending the admin into a form to tick one box, when the
   *     comparison they are making is between rows, is three clicks for a
   *     choice they already made.
   */
  const makeDefault = (zone: ShippingZone) => {
    saveZone.mutate(
      { id: zone.id, body: { is_default: true, governorates: [] } },
      { onSuccess: () => notify(t('shipping.defaultMoved'), 'success'), onError: fail },
    );
  };

  // ── Columns ─────────────────────────────────────────────

  const zoneColumns: Column<ShippingZone>[] = [
    {
      key: 'name',
      header: t('shipping.zone'),
      render: (row) => (
        <span>
          <code>{row.code}</code> — {row.name_ar}
          {row.is_default ? <Badge tone="info">{t('shipping.defaultZone')}</Badge> : null}
          {!row.is_active ? <Badge tone="neutral">{t('shipping.inactive')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'governorates',
      header: t('shipping.governorates'),
      render: (row) =>
        row.is_default
          ? t('shipping.everythingUnassigned')
          : row.governorates.join('، ') || '—',
    },
    {
      key: 'rates',
      header: t('shipping.rateCount'),
      align: 'end',
      // ⚠️  Zero is called out: a zone with no rate quotes nothing at all, and
      //     its customers see "no shipping available" at checkout.
      render: (row) =>
        row.rate_count === 0 ? (
          <Badge tone="warning">{t('shipping.noRates')}</Badge>
        ) : (
          row.rate_count
        ),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <span className="shipping-actions">
          <Button size="sm" variant="ghost" onClick={() => setEditingZone(row)}>
            {t('common.edit')}
          </Button>
          {!row.is_default ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                loading={saveZone.isPending}
                onClick={() => makeDefault(row)}
              >
                {t('shipping.makeDefault')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={removeZone.isPending}
                onClick={() => removeZone.mutate(row.id, deleted)}
              >
                {t('common.delete')}
              </Button>
            </>
          ) : null}
        </span>
      ),
    },
  ];

  const methodColumns: Column<AdminShippingMethod>[] = [
    {
      key: 'name',
      header: t('shipping.method'),
      render: (row) => (
        <span>
          <code>{row.code}</code> — {row.name_ar}
          {row.is_pickup ? <Badge tone="info">{t('shipping.pickup')}</Badge> : null}
          {!row.is_active ? <Badge tone="neutral">{t('shipping.inactive')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'days',
      header: t('shipping.estimate'),
      secondary: true,
      render: (row) =>
        t('shipping.daysRange', {
          min: row.estimated_days_min,
          max: row.estimated_days_max,
        }),
    },
    {
      key: 'order',
      header: t('shipping.displayOrder'),
      secondary: true,
      align: 'end',
      render: (row) => row.display_order,
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <span className="shipping-actions">
          <Button size="sm" variant="ghost" onClick={() => setEditingMethod(row)}>
            {t('common.edit')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={removeMethod.isPending}
            onClick={() => removeMethod.mutate(row.id, deleted)}
          >
            {t('common.delete')}
          </Button>
        </span>
      ),
    },
  ];

  const rateColumns: Column<ShippingRate>[] = [
    {
      key: 'pair',
      header: t('shipping.zone'),
      render: (row) => (
        <span>
          {row.zone_name} × {row.method_name}
          {!row.is_active ? <Badge tone="neutral">{t('shipping.inactive')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'base',
      header: t('shipping.baseFee'),
      align: 'end',
      render: (row) => formatMoney(row.base_fee, i18n.language),
    },
    {
      key: 'free',
      header: t('shipping.freeAbove'),
      align: 'end',
      // ⚠️  "—" rather than a blank: empty reads as "not loaded", and the
      //     difference between no free shipping and free above zero is the
      //     whole margin on this zone.
      render: (row) => (row.free_above ? formatMoney(row.free_above, i18n.language) : '—'),
    },
    {
      key: 'perKg',
      header: t('shipping.perKgFee'),
      secondary: true,
      align: 'end',
      render: (row) =>
        Number.parseFloat(row.per_kg_fee) === 0
          ? '—'
          : formatMoney(row.per_kg_fee, i18n.language),
    },
    {
      key: 'actions',
      header: t('admin.actions'),
      align: 'end',
      render: (row) => (
        <span className="shipping-actions">
          <Button size="sm" variant="ghost" onClick={() => setEditingRate(row)}>
            {t('common.edit')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={removeRate.isPending}
            onClick={() => removeRate.mutate(row.id, deleted)}
          >
            {t('common.delete')}
          </Button>
        </span>
      ),
    },
  ];

  const drawerOpen = creating || Boolean(editingZone ?? editingMethod ?? editingRate);

  return (
    <>
      <PageHeader
        title={t('shipping.setupTitle')}
        description={t('shipping.setupHint')}
        actions={<Button onClick={() => setCreating(true)}>{t(`shipping.new_${tab}`)}</Button>}
      />

      {/* ⚠️  Two failures the panel cannot show by staying silent about them.
          With no default zone every unassigned governorate quotes nothing, and
          the customer reads "no shipping available" — a checkout that cannot
          complete, caused by a setting nobody was asked about. */}
      {coverage.data && !coverage.data.has_default_zone ? (
        <Alert tone="danger">{t('shipping.noDefaultZoneWarning')}</Alert>
      ) : null}

      {coverage.data && coverage.data.unassigned.length > 0 ? (
        <Alert tone="warning">
          {t('shipping.unassignedWarning', {
            count: coverage.data.unassigned.length,
            zone: coverage.data.default_zone_code,
          })}
          <br />
          <small className="shipping-unassigned">{coverage.data.unassigned.join('، ')}</small>
        </Alert>
      ) : null}

      <StatusTabs
        options={[
          { value: 'zones', label: t('shipping.zones') },
          { value: 'methods', label: t('shipping.methods') },
          { value: 'rates', label: t('shipping.rates') },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next as Tab);
          closeDrawer();
        }}
      />

      {tab === 'zones' ? (
        <DataTable
          columns={zoneColumns}
          rows={zones.data ?? []}
          rowKey={(row) => row.id}
          isLoading={zones.isPending}
          error={zones.error}
          emptyTitle={t('shipping.noZones')}
          emptyBody={t('shipping.noZonesBody')}
        />
      ) : null}

      {tab === 'methods' ? (
        <DataTable
          columns={methodColumns}
          rows={methods.data ?? []}
          rowKey={(row) => row.id}
          isLoading={methods.isPending}
          error={methods.error}
          emptyTitle={t('shipping.noMethods')}
          emptyBody={t('shipping.noMethodsBody')}
        />
      ) : null}

      {tab === 'rates' ? (
        <DataTable
          columns={rateColumns}
          rows={rates.data ?? []}
          rowKey={(row) => row.id}
          isLoading={rates.isPending}
          error={rates.error}
          emptyTitle={t('shipping.noRatesTitle')}
          emptyBody={t('shipping.noRatesBody')}
        />
      ) : null}

      <Drawer
        open={drawerOpen}
        onClose={closeDrawer}
        title={t(creating ? `shipping.new_${tab}` : 'common.edit')}
      >
        {(creating && tab === 'zones') || editingZone ? (
          <ShippingZoneForm zone={editingZone ?? undefined} onDone={closeDrawer} />
        ) : null}

        {(creating && tab === 'methods') || editingMethod ? (
          <ShippingMethodForm method={editingMethod ?? undefined} onDone={closeDrawer} />
        ) : null}

        {(creating && tab === 'rates') || editingRate ? (
          <ShippingRateForm rate={editingRate ?? undefined} onDone={closeDrawer} />
        ) : null}
      </Drawer>
    </>
  );
}
