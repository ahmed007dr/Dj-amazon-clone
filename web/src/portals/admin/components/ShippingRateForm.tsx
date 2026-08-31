import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ShippingRate } from '@/features/shipping/api';
import {
  useAdminShippingMethods,
  useSaveRate,
  useShippingZones,
} from '@/features/shipping/hooks';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './ShippingForms.css';

/**
 * The fee for one zone × one method.
 *
 * ⚠️  `free_above` is **per row, and that is the whole point** (business rule
 *     in `shipping/models.py`).
 *
 *     A single global "free above 500" imposes Cairo's economics on Upper
 *     Egypt, where the delivery genuinely costs more — so every free order
 *     there ships at a loss, on every single one. Empty here means no free
 *     shipping *for this zone*, which is a different setting from zero.
 *
 * ⚠️  The zone and the method are locked once the row exists.
 *
 *     Moving a rate to another pair is not an edit, it is a different rate —
 *     and the pair is unique, so the "edit" silently collides with a row the
 *     admin cannot see from here.
 */
export function ShippingRateForm({
  rate,
  onDone,
}: {
  rate?: ShippingRate | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const save = useSaveRate();
  const zones = useShippingZones();
  const methods = useAdminShippingMethods();

  const [form, setForm] = useState({
    zone: rate?.zone ?? '',
    method: rate?.method ?? '',
    base_fee: rate?.base_fee ?? '0.00',
    free_above: rate?.free_above ?? '',
    per_kg_fee: rate?.per_kg_fee ?? '0.00',
    is_active: rate?.is_active ?? true,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set =
    <K extends keyof typeof form>(key: K) =>
    (value: (typeof form)[K]) => {
      setForm((current) => ({ ...current, [key]: value }));
    };

  const pickedMethod = methods.data?.find((entry) => entry.id === form.method);

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      base_fee: form.base_fee || '0',
      // ⚠️  Empty = no free shipping for this zone. Sent as `null`, not as an
      //     empty string, which the server refuses as an invalid number.
      free_above: form.free_above.trim() ? form.free_above : null,
      per_kg_fee: form.per_kg_fee || '0',
      is_active: form.is_active,
    };
    if (!rate) {
      body.zone = form.zone;
      body.method = form.method;
    }

    save.mutate(
      { ...(rate ? { id: rate.id } : {}), body },
      {
        onSuccess: () => {
          notify(t('shipping.saved'), 'success');
          onDone();
        },
        onError: (error) => {
          if (isApiError(error)) {
            const next: Record<string, string> = {};
            for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
            setFieldErrors(next);
            notify(error.displayMessage, 'danger');
            return;
          }
          notify(t('state.errorTitle'), 'danger');
        },
      },
    );
  };

  const errorFor = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  return (
    <div className="shipping-form">
      {rate ? (
        <p className="shipping-form__pair">
          <strong>{rate.zone_name}</strong> × <strong>{rate.method_name}</strong>
        </p>
      ) : (
        <div className="shipping-form__row">
          <label className="shipping-form__select">
            <span>{t('shipping.zone')}</span>
            <select value={form.zone} onChange={(event) => set('zone')(event.target.value)}>
              <option value="">{t('shipping.chooseZone')}</option>
              {zones.data?.map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {zone.name_ar}
                </option>
              ))}
            </select>
            {fieldErrors.zone ? (
              <span className="shipping-form__error">{fieldErrors.zone}</span>
            ) : null}
          </label>

          <label className="shipping-form__select">
            <span>{t('shipping.method')}</span>
            <select value={form.method} onChange={(event) => set('method')(event.target.value)}>
              <option value="">{t('shipping.chooseMethod')}</option>
              {methods.data?.map((method) => (
                <option key={method.id} value={method.id}>
                  {method.name_ar}
                </option>
              ))}
            </select>
            {fieldErrors.method ? (
              <span className="shipping-form__error">{fieldErrors.method}</span>
            ) : null}
          </label>
        </div>
      )}

      {/* ⚠️  A pickup method is quoted at zero whatever is typed here — saying so
          beats letting the admin set 30 and watch the checkout ignore it. */}
      {(pickedMethod?.is_pickup ?? rate?.method_is_pickup) ? (
        <Alert tone="info">{t('shipping.pickupRateNote')}</Alert>
      ) : null}

      <div className="shipping-form__row">
        <Field
          label={t('shipping.baseFee')}
          value={form.base_fee}
          onChange={(event) => set('base_fee')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          {...errorFor('base_fee')}
        />
        <Field
          label={t('shipping.freeAbove')}
          value={form.free_above}
          onChange={(event) => set('free_above')(event.target.value)}
          inputMode="decimal"
          dir="ltr"
          hint={t('shipping.freeAboveHint')}
          {...errorFor('free_above')}
        />
      </div>

      <Field
        label={t('shipping.perKgFee')}
        value={form.per_kg_fee}
        onChange={(event) => set('per_kg_fee')(event.target.value)}
        inputMode="decimal"
        dir="ltr"
        hint={t('shipping.perKgFeeHint')}
        {...errorFor('per_kg_fee')}
      />

      <label className="shipping-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active')(event.target.checked)}
        />
        <span>
          {t('reference.isActive')}
          <small>{t('shipping.rateActiveHint')}</small>
        </span>
      </label>

      <div className="shipping-form__actions">
        <Button
          onClick={submit}
          loading={save.isPending}
          disabled={!rate && (!form.zone || !form.method)}
        >
          {t('common.save')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={save.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
