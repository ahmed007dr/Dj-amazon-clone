import { useState } from 'react';
import { useTranslation } from 'react-i18next';

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
 * تنفيذ حركة مخزون.
 *
 * ⚠️  **نموذج واحد لأربع عمليات لا أربعة نماذج.**
 *
 *     الأربع تتشارك المنتج والموقع والكمية؛ وتفرّقها حقول قليلة.
 *     أربع نسخ كانت تعني أن إصلاح منتقي المنتج يحتاج أربعة تعديلات
 *     — وأن المنسيّ منها يبقى معطوبًا.
 *
 * ⚠️  و**كل حركة تُسجَّل ولا تُمحى**. التصحيح بحركة معاكسة لا
 *     بتحرير القديمة — ولذلك لا يوجد هنا زر تعديل ولا حذف.
 *
 * ⚠️  والسبب **إلزامي** في التسوية والتلف.
 *
 *     تسوية بلا سبب ثغرة في الجرد: الفرق يظهر بعد شهر ولا أحد
 *     يعرف إن كان سرقة أو خطأ عدّ أو تلفًا لم يُسجَّل.
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

  const receive = useReceiveStock();
  const adjust = useAdjustStock();
  const transfer = useTransferStock();
  const damage = useMarkDamaged();

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
          // ⚠️  الإشارة من زرّي الاتجاه لا من كتابة `-` في الحقل.
          //     السالب المكتوب يدويًا يُنسى، فتُسجَّل زيادة مكان نقص.
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
    (!needsReason || reason.trim().length >= 3);

  const locationOptions = locations.map((row) => ({
    value: row.id,
    label: `${row.code} — ${localized(row, 'name')}`,
  }));

  return (
    <div className="stock-form">
      <p className="stock-form__intro">{t(`inventory.intro_${action}`)}</p>

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
          placeholder={t('inventory.defaultLocation')}
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
 * ⚠️  الموقع الافتراضي مُنتقى مسبقًا.
 *
 *     أغلب المنشآت لها مخزن واحد؛ وإجبار الأدمن على اختياره في كل
 *     حركة خطوة بلا قرار.
 */
function defaultLocation(locations: StockLocation[]): string {
  return locations.find((row) => row.is_default)?.id ?? '';
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
