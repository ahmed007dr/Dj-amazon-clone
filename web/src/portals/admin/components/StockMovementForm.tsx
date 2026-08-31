import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useCan } from '@/features/auth/useCan';
import type { AdminProduct } from '@/features/catalog/adminApi';
import {
  useAdjustStock,
  useMarkDamaged,
  useReceiveStock,
  useTransferStock,
  type StockLocation,
} from '@/features/inventory/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import { ProductPicker } from './ProductPicker';

import './StockMovementForm.css';

export type MovementAction = 'receive' | 'adjust' | 'transfer' | 'damage';

/**
 * Performing a stock movement.
 *
 * ⚠️  **One form for four operations, not four forms.**
 *
 *     All four share the product, the location and the quantity; a few fields
 *     separate them. Four copies would have meant fixing the product picker
 *     takes four edits — and that the forgotten one stays broken.
 *
 * ⚠️  And **every movement is recorded and never erased**. Corrections go
 *     through an offsetting movement rather than editing the old one — which is
 *     why there is no edit and no delete button here.
 *
 * ⚠️  And the reason is **mandatory** for adjustments and damage.
 *
 *     An adjustment with no reason is a hole in the stock count: the
 *     discrepancy appears a month later and nobody knows whether it was theft,
 *     a counting error, or damage that went unrecorded.
 */
export function StockMovementForm({
  action,
  locations,
  onDone,
}: {
  action: MovementAction;
  locations: StockLocation[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const localized = useLocalized();

  // ⚠️  **Managing locations is a different permission from managing stock.**
  //
  //     `inventory.change_stock` opens this form; `inventory.change_stocklocation`
  //     opens the screen that fixes it. Someone holding only the first is blocked
  //     by a message pointing at a screen their sidebar does not show and their
  //     account cannot open — so the link is offered only to whoever can act on
  //     it, and everyone else is told to ask, which is the real next step.
  const can = useCan();
  const canManageLocations = can('inventory.change_stocklocation');

  const receive = useReceiveStock();
  const adjust = useAdjustStock();
  const transfer = useTransferStock();
  const damage = useMarkDamaged();

  // ⚠️  The usable locations — a deactivated one is not somewhere stock can go.
  const usable = locations.filter((row) => row.is_active);

  // ⚠️  **Whether a fallback exists at all**, and the form changes shape on it.
  //
  //     Leaving `location` empty makes the server fall back to its default. That
  //     is a convenience when a default exists and a trap when none does: the
  //     field showed the placeholder "الموقع الافتراضي", which reads as a chosen
  //     value rather than an empty one, the submit button stayed enabled, and the
  //     refusal arrived from the server naming a concept the admin never picked.
  const hasDefault = defaultLocation(locations) !== '';

  const [product, setProduct] = useState<AdminProduct | null>(null);
  const [location, setLocation] = useState(() => defaultLocation(locations));
  const [toLocation, setToLocation] = useState('');
  const [quantity, setQuantity] = useState('');
  const [direction, setDirection] = useState<'up' | 'down'>('down');
  const [unitCost, setUnitCost] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [batchNumber, setBatchNumber] = useState('');
  const [reason, setReason] = useState('');

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const pending =
    receive.isPending || adjust.isPending || transfer.isPending || damage.isPending;

  const onError = (error: unknown) => {
    if (isApiError(error)) {
      const next: Record<string, string> = {};
      for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
      setFieldErrors(next);
      notify(error.displayMessage, 'danger');
      return;
    }
    notify(t('state.errorTitle'), 'danger');
  };

  const done = () => {
    notify(t(`inventory.done_${action}`), 'success');
    onDone();
  };

  const submit = () => {
    setFieldErrors({});
    if (product === null) return;

    const count = Number(quantity);

    if (action === 'receive') {
      receive.mutate(
        {
          product: product.id,
          location: location || null,
          quantity: count,
          unit_cost: unitCost,
          expires_at: expiresAt || null,
          supplier_batch_number: batchNumber,
        },
        { onSuccess: done, onError },
      );
      return;
    }

    if (action === 'adjust') {
      adjust.mutate(
        {
          product: product.id,
          location: location || null,
          // ⚠️  The sign comes from the two direction buttons, not from typing `-` in the field.
          //     A hand-written minus gets forgotten, so an increase is recorded in place of a decrease.
          quantity: direction === 'down' ? -count : count,
          reason,
        },
        { onSuccess: done, onError },
      );
      return;
    }

    if (action === 'transfer') {
      transfer.mutate(
        {
          product: product.id,
          from_location: location,
          to_location: toLocation,
          quantity: count,
        },
        { onSuccess: done, onError },
      );
      return;
    }

    damage.mutate(
      {
        product: product.id,
        location: location || null,
        quantity: count,
        reason,
      },
      { onSuccess: done, onError },
    );
  };

  const needsReason = action === 'adjust' || action === 'damage';
  const positiveCount = Number(quantity) > 0;

  const ready =
    product !== null &&
    quantity !== '' &&
    positiveCount &&
    (action !== 'receive' || unitCost !== '') &&
    (action !== 'transfer' || (location !== '' && toLocation !== '' && location !== toLocation)) &&
    // ⚠️  With no default to fall back on, the location stops being optional.
    (hasDefault || location !== '') &&
    (!needsReason || reason.trim().length >= 3);

  const locationOptions = usable.map((row) => ({
    value: row.id,
    label: `${row.code} — ${localized(row, 'name')}`,
  }));

  // ⚠️  No location at all is not a form to be filled in more carefully — there is
  //     nowhere for the stock to go. Saying so, and where to fix it, beats an
  //     empty dropdown above a button that fails.
  if (usable.length === 0) {
    return (
      <div className="stock-form">
        <Alert tone="warning">
          {/* ⚠️  A link, not the screen's name.
              Naming it was worse than useless: the locations live under a
              different sidebar section from inventory, behind a different
              permission — so the message named a screen the reader may not be
              shown, under a label that says nothing about stock. */}
          {t('inventory.noLocations')}{' '}
          {canManageLocations ? (
            <Link to="/admin/settings">{t('inventory.manageLocations')}</Link>
          ) : (
            t('inventory.askAnAdmin')
          )}
        </Alert>
      </div>
    );
  }

  return (
    <div className="stock-form">
      <p className="stock-form__intro">{t(`inventory.intro_${action}`)}</p>

      {/* ⚠️  Stated once, at the top: every field below behaves differently without it. */}
      {hasDefault ? null : (
        <Alert tone="info">
          {t('inventory.noDefaultLocation')}{' '}
          {canManageLocations ? (
            <Link to="/admin/settings">{t('inventory.manageLocations')}</Link>
          ) : (
            t('inventory.askAnAdmin')
          )}
        </Alert>
      )}

      <ProductPicker
        value={product}
        onChange={setProduct}
        {...(fieldErrors.product ? { error: fieldErrors.product } : {})}
      />

      {action === 'transfer' ? (
        <div className="stock-form__row">
          <Select
            label={t('inventory.fromLocation')}
            value={location}
            onChange={setLocation}
            options={locationOptions}
            placeholder={t('common.choose')}
            {...(fieldErrors.from_location ? { error: fieldErrors.from_location } : {})}
          />
          <Select
            label={t('inventory.toLocation')}
            value={toLocation}
            onChange={setToLocation}
            options={locationOptions}
            placeholder={t('common.choose')}
            {...(fieldErrors.to_location ? { error: fieldErrors.to_location } : {})}
          />
        </div>
      ) : (
        <Select
          label={t('admin.location')}
          value={location}
          onChange={setLocation}
          options={locationOptions}
          // ⚠️  The placeholder tells the truth about what an empty value means:
          //     with a default it is "fall back to it", without one it is "not
          //     chosen yet" — and a select with no empty option would *display*
          //     the first location while holding no value, which is the same lie
          //     in a new place.
          placeholder={hasDefault ? t('inventory.defaultLocation') : t('common.choose')}
          {...(fieldErrors.location ? { error: fieldErrors.location } : {})}
        />
      )}

      {action === 'adjust' ? (
        <fieldset className="stock-form__direction">
          <legend>{t('inventory.direction')}</legend>
          <label>
            <input
              type="radio"
              name="direction"
              checked={direction === 'down'}
              onChange={() => setDirection('down')}
            />
            {t('inventory.decrease')}
          </label>
          <label>
            <input
              type="radio"
              name="direction"
              checked={direction === 'up'}
              onChange={() => setDirection('up')}
            />
            {t('inventory.increase')}
          </label>
        </fieldset>
      ) : null}

      <div className="stock-form__row">
        <Field
          label={t('inventory.quantity')}
          value={quantity}
          onChange={(event) => setQuantity(event.target.value.replace(/[^\d]/g, ''))}
          inputMode="numeric"
          dir="ltr"
          required
          {...(fieldErrors.quantity ? { error: fieldErrors.quantity } : {})}
        />

        {action === 'receive' ? (
          <Field
            label={t('inventory.unitCost')}
            value={unitCost}
            onChange={(event) => setUnitCost(event.target.value)}
            inputMode="decimal"
            dir="ltr"
            required
            hint={t('inventory.unitCostHint')}
            {...(fieldErrors.unit_cost ? { error: fieldErrors.unit_cost } : {})}
          />
        ) : null}
      </div>

      {action === 'receive' ? (
        <div className="stock-form__row">
          <Field
            label={t('inventory.expiresAt')}
            type="date"
            value={expiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
            hint={t('inventory.expiresAtHint')}
            {...(fieldErrors.expires_at ? { error: fieldErrors.expires_at } : {})}
          />
          <Field
            label={t('inventory.supplierBatch')}
            value={batchNumber}
            onChange={(event) => setBatchNumber(event.target.value)}
            dir="ltr"
            {...(fieldErrors.supplier_batch_number
              ? { error: fieldErrors.supplier_batch_number }
              : {})}
          />
        </div>
      ) : null}

      {needsReason ? (
        <label className="stock-form__reason">
          <span>
            {t('inventory.reason')}
            <em aria-hidden> *</em>
          </span>
          <textarea
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t(`inventory.reasonPlaceholder_${action}`)}
          />
          {fieldErrors.reason ? (
            <span className="stock-form__error" role="alert">
              {fieldErrors.reason}
            </span>
          ) : null}
        </label>
      ) : null}

      {action === 'damage' ? <Alert tone="warning">{t('inventory.damageNote')}</Alert> : null}
      {action === 'adjust' ? <Alert tone="info">{t('inventory.adjustNote')}</Alert> : null}

      <div className="stock-form__actions">
        <Button onClick={submit} loading={pending} disabled={!ready}>
          {t(`inventory.submit_${action}`)}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={pending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}

/**
 * ⚠️  The default location is pre-selected.
 *
 *     Most businesses have one warehouse; and forcing the admin to choose it on
 *     every movement is a step with no decision in it.
 */
function defaultLocation(locations: StockLocation[]): string {
  // ⚠️  `is_active` too — the server's `get_default()` requires it.
  //
  //     A location can carry the default tick and be switched off, and the
  //     settings screen goes on showing the tick. Matching on the flag alone
  //     preselected nothing while the field still read "the default location",
  //     and the movement was refused with "there is no default location" — a
  //     server contradicting a screen the admin was looking at.
  return locations.find((row) => row.is_default && row.is_active)?.id ?? '';
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder,
  error,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  error?: string;
}) {
  return (
    <label className="stock-form__select">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <span className="stock-form__error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}
