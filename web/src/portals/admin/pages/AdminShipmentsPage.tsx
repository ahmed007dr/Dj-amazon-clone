import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ALLOWED_TRANSITIONS,
  type Shipment,
  type ShipmentStatus,
} from '@/features/shipping/api';
import { useAdminShipments, useTransitionShipment } from '@/features/shipping/hooks';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { DataTable, type Column } from '@/shared/tables/DataTable';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Modal } from '@/shared/ui/Modal';
import { Pagination } from '@/shared/ui/Pagination';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatDate, formatMoney } from '@/shared/utils/format';

const STATUSES: ('' | ShipmentStatus)[] = [
  '',
  'PENDING',
  'PICKED',
  'IN_TRANSIT',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
  'FAILED',
  'RETURNED',
];

const TONE: Record<ShipmentStatus, 'neutral' | 'info' | 'success' | 'warning' | 'danger'> = {
  PENDING: 'neutral',
  PICKED: 'info',
  IN_TRANSIT: 'info',
  OUT_FOR_DELIVERY: 'warning',
  DELIVERED: 'success',
  FAILED: 'danger',
  RETURNED: 'danger',
};

export function AdminShipmentsPage() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [status, setStatus] = useState<'' | ShipmentStatus>('PENDING');
  const [page, setPage] = useState(1);

  // The shipment being moved — null closes the dialog
  const [moving, setMoving] = useState<Shipment | null>(null);
  const [target, setTarget] = useState<ShipmentStatus | ''>('');
  const [note, setNote] = useState('');
  const [location, setLocation] = useState('');
  const [trackingNumber, setTrackingNumber] = useState('');

  const query = useAdminShipments({ ...(status ? { status } : {}), page });
  const transition = useTransitionShipment();

  const openMove = (shipment: Shipment) => {
    setMoving(shipment);
    // ⚠️  Preselecting the only legal next step: with one option, asking the
    //     operator to pick it is a click that carries no decision.
    const next = ALLOWED_TRANSITIONS[shipment.status];
    setTarget(next.length === 1 ? (next[0] as ShipmentStatus) : '');
    setNote('');
    setLocation('');
    setTrackingNumber(shipment.tracking_number);
  };

  const submitMove = () => {
    if (!moving || !target) return;

    transition.mutate(
      {
        id: moving.id,
        status: target,
        note,
        location,
        // ⚠️  Sent only when it changed: an unchanged value on every transition
        //     rewrites the carrier's number with itself and fills the event log
        //     with edits that record nothing.
        ...(trackingNumber !== moving.tracking_number ? { tracking_number: trackingNumber } : {}),
      },
      {
        onSuccess: () => {
          notify(t('shipping.transitioned'), 'success');
          setMoving(null);
        },
        // ⚠️  A refused transition arrives as 409 from the state machine and its
        //     message names the reason. Showing the server's text rather than a
        //     generic failure is the difference between "try again" and
        //     "a delivered shipment does not go back".
        onError: (cause) =>
          notify(
            isApiError(cause) ? cause.displayMessage : t('shipping.transitionFailed'),
            'danger',
          ),
      },
    );
  };

  const columns: Column<Shipment>[] = [
    {
      key: 'number',
      header: t('shipping.number'),
      render: (shipment) => <strong style={{ direction: 'ltr' }}>{shipment.number}</strong>,
    },
    {
      key: 'status',
      header: t('admin.status'),
      render: (shipment) => (
        <Badge tone={TONE[shipment.status]}>{t(`shipmentStatus.${shipment.status}`)}</Badge>
      ),
    },
    {
      key: 'method',
      header: t('shipping.method'),
      render: (shipment) => shipment.method_name,
    },
    {
      key: 'destination',
      header: t('shipping.destination'),
      render: (shipment) => [shipment.governorate, shipment.city].filter(Boolean).join(' — '),
    },
    {
      key: 'carrier',
      header: t('shipping.carrier'),
      render: (shipment) => (
        <span style={{ direction: 'ltr', display: 'inline-block' }}>
          {shipment.tracking_number || shipment.carrier || '—'}
        </span>
      ),
    },
    {
      key: 'fee',
      header: t('shipping.fee'),
      align: 'end',
      render: (shipment) => formatMoney(shipment.shipping_fee, i18n.language),
    },
    {
      key: 'shipped',
      header: t('shipping.shippedAt'),
      render: (shipment) => formatDate(shipment.shipped_at, i18n.language),
    },
    {
      key: 'move',
      header: '',
      render: (shipment) => {
        const next = ALLOWED_TRANSITIONS[shipment.status];
        // ⚠️  A terminal shipment shows no button at all rather than a disabled
        //     one: there is nothing to wait for, and a greyed control invites a
        //     click that will never work.
        if (next.length === 0) return null;

        return (
          <Button variant="secondary" size="sm" onClick={() => openMove(shipment)}>
            {t('shipping.move')}
          </Button>
        );
      },
    },
  ];

  const options = moving ? ALLOWED_TRANSITIONS[moving.status] : [];

  return (
    <>
      <PageHeader
        title={t('nav.shipments')}
        {...(query.data ? { description: t('admin.total', { count: query.data.count }) } : {})}
      />

      <StatusTabs
        options={STATUSES.map((value) => ({
          value,
          label: value ? t(`shipmentStatus.${value}`) : t('common.all'),
        }))}
        value={status}
        onChange={(next) => {
          setStatus(next as '' | ShipmentStatus);
          // Staying on page 7 of a two-page result shows an empty list
          setPage(1);
        }}
      />

      <DataTable
        columns={columns}
        rows={query.data?.results ?? []}
        rowKey={(shipment) => shipment.id}
        isLoading={query.isPending}
        error={query.error}
        emptyTitle={t('shipping.noShipments')}
      />

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Modal
        open={moving !== null}
        onClose={() => setMoving(null)}
        title={moving ? `${t('shipping.move')} — ${moving.number}` : ''}
        footer={
          <>
            <Button disabled={!target} loading={transition.isPending} onClick={submitMove}>
              {t('common.confirm')}
            </Button>
            <Button variant="ghost" onClick={() => setMoving(null)}>
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        {/* ⚠️  Only the moves the state machine permits are offered. The server
            checks again — this narrows the choice, it does not grant it. */}
        <label className="field">
          <span className="field__label">{t('shipping.newStatus')}</span>
          <select
            className="field__input"
            value={target}
            onChange={(event) => setTarget(event.target.value as ShipmentStatus)}
          >
            <option value="">{t('shipping.chooseStatus')}</option>
            {options.map((value) => (
              <option key={value} value={value}>
                {t(`shipmentStatus.${value}`)}
              </option>
            ))}
          </select>
        </label>

        <Field
          label={t('shipping.location')}
          value={location}
          onChange={(event) => setLocation(event.target.value)}
          hint={t('shipping.locationHint')}
        />

        <Field
          label={t('shipping.trackingNumber')}
          value={trackingNumber}
          onChange={(event) => setTrackingNumber(event.target.value)}
          style={{ direction: 'ltr' }}
        />

        <Field
          label={t('shipping.note')}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </Modal>
    </>
  );
}
