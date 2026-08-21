import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useCreateOrder,
  useSupplierOffers,
  type Supplier,
  type SupplierOffer,
} from '@/features/suppliers/api';
import { useInventoryLocations } from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './NewPurchaseOrder.css';

interface Line {
  offer: SupplierOffer;
  quantity: number;
  unitCost: string;
}

/**
 * Creating a purchase order.
 *
 * ⚠️  **The items are chosen from this supplier's offers alone.**
 *
 *     A list of every product makes the buyer order an item this supplier does
 *     not sell — and the server discovers it with a refusal after the whole
 *     order has been built.
 *
 * ⚠️  And the price is **filled in from the offer and editable**.
 *
 *     Purchasing is negotiated. And the difference is stored and recorded in
 *     the audit log, and does not touch the offer itself — so the next order
 *     starts from the original price.
 */
export function NewPurchaseOrder({
  supplier,
  onDone,
}: {
  supplier: Supplier;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [lines, setLines] = useState<Line[]>([]);
  const [location, setLocation] = useState('');
  const [expectedOn, setExpectedOn] = useState('');
  const [note, setNote] = useState('');

  const offers = useSupplierOffers(supplier.id);
  const locations = useInventoryLocations();
  const create = useCreateOrder();

  const available = (offers.data?.results ?? []).filter(
    (offer) => offer.is_active && !lines.some((line) => line.offer.id === offer.id),
  );

  const add = (offer: SupplierOffer) =>
    setLines((current) => [
      ...current,
      {
        offer,
        // ⚠️  The quantity starts at the minimum order rather than at 1: starting
        //     at one makes the server refuse every line until it is corrected by hand.
        quantity: offer.minimum_order_quantity,
        unitCost: offer.unit_cost,
      },
    ]);

  const update = (id: string, patch: Partial<Line>) =>
    setLines((current) =>
      current.map((line) => (line.offer.id === id ? { ...line, ...patch } : line)),
    );

  const remove = (id: string) =>
    setLines((current) => current.filter((line) => line.offer.id !== id));

  const subtotal = lines.reduce(
    (sum, line) => sum + Number(line.unitCost || 0) * line.quantity,
    0,
  );

  const belowMinimum = lines.filter(
    (line) => line.quantity < line.offer.minimum_order_quantity,
  );

  const ready = lines.length > 0 && location !== '' && belowMinimum.length === 0;

  if (offers.isPending) return <Spinner />;

  return (
    <div className="new-po">
      <h3>{t('suppliers.newOrder')}</h3>

      {available.length === 0 && lines.length === 0 ? (
        <StateMessage
          icon="▤"
          title={t('suppliers.noOffers')}
          body={t('suppliers.noOffersBody')}
        />
      ) : null}

      {available.length > 0 ? (
        <label className="new-po__picker">
          {t('suppliers.addProduct')}
          <select
            value=""
            onChange={(event) => {
              const offer = available.find((row) => row.id === event.target.value);
              if (offer) add(offer);
            }}
          >
            <option value="">{t('common.choose')}</option>
            {available.map((offer) => (
              <option key={offer.id} value={offer.id}>
                {localized(offer, 'product_name')} · {offer.unit_cost}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <ul className="new-po__lines">
        {lines.map((line) => (
          <li key={line.offer.id}>
            <span className="truncate">{localized(line.offer, 'product_name')}</span>

            <label className="new-po__field">
              {t('suppliers.quantity')}
              <input
                type="number"
                min={line.offer.minimum_order_quantity}
                dir="ltr"
                value={line.quantity}
                onChange={(event) =>
                  update(line.offer.id, { quantity: Number(event.target.value) || 0 })
                }
              />
            </label>

            <label className="new-po__field">
              {t('suppliers.unitCost')}
              <input
                type="number"
                min="0"
                step="0.01"
                dir="ltr"
                value={line.unitCost}
                onChange={(event) => update(line.offer.id, { unitCost: event.target.value })}
              />
              {/* ⚠️  The offer price is shown beneath the field: without it the
                  buyer does not know they changed it, nor by how much. */}
              {line.unitCost !== line.offer.unit_cost ? (
                <span className="new-po__was">
                  {t('suppliers.wasPriced', { price: line.offer.unit_cost })}
                </span>
              ) : null}
            </label>

            <button
              type="button"
              className="new-po__remove"
              aria-label={t('common.delete')}
              onClick={() => remove(line.offer.id)}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      {belowMinimum.length > 0 ? (
        <Alert tone="warning">
          {t('suppliers.belowMinimum', {
            items: belowMinimum
              .map((line) => `${line.offer.product_sku} (${line.offer.minimum_order_quantity})`)
              .join('، '),
          })}
        </Alert>
      ) : null}

      <label className="new-po__picker">
        {t('suppliers.receiveAt')}
        <select value={location} onChange={(event) => setLocation(event.target.value)}>
          <option value="">{t('common.choose')}</option>
          {(locations.data ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {localized(row, 'name')} · {row.code}
            </option>
          ))}
        </select>
      </label>

      <label className="new-po__picker">
        {t('suppliers.expectedOn')}
        <input
          type="date"
          value={expectedOn}
          onChange={(event) => setExpectedOn(event.target.value)}
        />
      </label>

      <label className="new-po__picker">
        {t('suppliers.note')}
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>

      <div className="new-po__total">
        <span>{t('suppliers.subtotal')}</span>
        <strong dir="ltr">{subtotal.toFixed(2)}</strong>
      </div>

      {create.error ? (
        <Alert tone="danger">
          {isApiError(create.error) ? create.error.displayMessage : t('state.errorTitle')}
        </Alert>
      ) : null}

      <div className="new-po__actions">
        <Button variant="secondary" onClick={onDone}>
          {t('common.cancel')}
        </Button>
        <Button
          loading={create.isPending}
          disabled={!ready}
          onClick={() =>
            create.mutate(
              {
                supplier: supplier.id,
                location,
                lines: lines.map((line) => ({
                  product: line.offer.product,
                  quantity: line.quantity,
                  unit_cost: line.unitCost,
                })),
                ...(expectedOn ? { expected_on: expectedOn } : {}),
                ...(note ? { note } : {}),
              },
              { onSuccess: onDone },
            )
          }
        >
          {t('suppliers.createOrder')}
        </Button>
      </div>
    </div>
  );
}
