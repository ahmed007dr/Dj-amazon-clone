import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AdminShippingMethod } from '@/features/shipping/api';
import { useSaveMethod } from '@/features/shipping/hooks';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { useToast } from '@/shared/ui/useToast';

import './ShippingForms.css';

/**
 * A shipping method — standard · express · collect from the branch.
 *
 * ⚠️  `is_pickup` is **not a label**: the server forces the fee to zero for it
 *     and the checkout stops asking for an address.
 *
 *     Which is why the switch carries a warning rather than sitting quietly
 *     among the others — flipping it on a method already in use changes how the
 *     orders carrying it behave, not just how the option reads.
 */
export function ShippingMethodForm({
  method,
  onDone,
}: {
  method?: AdminShippingMethod | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { notify } = useToast();

  const save = useSaveMethod();

  const [form, setForm] = useState({
    code: method?.code ?? '',
    name_ar: method?.name_ar ?? '',
    name_en: method?.name_en ?? '',
    description_ar: method?.description_ar ?? '',
    description_en: method?.description_en ?? '',
    estimated_days_min: String(method?.estimated_days_min ?? 1),
    estimated_days_max: String(method?.estimated_days_max ?? 3),
    is_pickup: method?.is_pickup ?? false,
    display_order: String(method?.display_order ?? 0),
    is_active: method?.is_active ?? true,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set =
    <K extends keyof typeof form>(key: K) =>
    (value: (typeof form)[K]) => {
      setForm((current) => ({ ...current, [key]: value }));
    };

  const submit = () => {
    setFieldErrors({});

    const body: Record<string, unknown> = {
      name_ar: form.name_ar,
      name_en: form.name_en,
      description_ar: form.description_ar,
      description_en: form.description_en,
      estimated_days_min: Number(form.estimated_days_min) || 0,
      estimated_days_max: Number(form.estimated_days_max) || 0,
      is_pickup: form.is_pickup,
      display_order: Number(form.display_order) || 0,
      is_active: form.is_active,
    };
    if (!method) body.code = form.code;

    save.mutate(
      { ...(method ? { id: method.id } : {}), body },
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
      <div className="shipping-form__row">
        <Field
          label={t('settings.code')}
          value={form.code}
          onChange={(event) => set('code')(event.target.value)}
          disabled={Boolean(method)}
          dir="ltr"
          required
          {...(method ? { hint: t('settings.codeLocked') } : {})}
          {...errorFor('code')}
        />
        <Field
          label={t('products.nameAr')}
          value={form.name_ar}
          onChange={(event) => set('name_ar')(event.target.value)}
          required
          {...errorFor('name_ar')}
        />
      </div>

      <Field
        label={t('products.nameEn')}
        value={form.name_en}
        onChange={(event) => set('name_en')(event.target.value)}
        dir="ltr"
        {...errorFor('name_en')}
      />

      {/* ⚠️  The description is what the customer reads under the option at
          checkout — "يصل خلال يومين داخل القاهرة" answers the question the
          delivery estimate alone does not. */}
      <Field
        label={t('shipping.descriptionAr')}
        value={form.description_ar}
        onChange={(event) => set('description_ar')(event.target.value)}
        hint={t('shipping.descriptionHint')}
        {...errorFor('description_ar')}
      />

      <Field
        label={t('shipping.descriptionEn')}
        value={form.description_en}
        onChange={(event) => set('description_en')(event.target.value)}
        dir="ltr"
        {...errorFor('description_en')}
      />

      <div className="shipping-form__row">
        <Field
          label={t('shipping.daysMin')}
          value={form.estimated_days_min}
          onChange={(event) => set('estimated_days_min')(event.target.value)}
          inputMode="numeric"
          dir="ltr"
          {...errorFor('estimated_days_min')}
        />
        <Field
          label={t('shipping.daysMax')}
          value={form.estimated_days_max}
          onChange={(event) => set('estimated_days_max')(event.target.value)}
          inputMode="numeric"
          dir="ltr"
          {...errorFor('estimated_days_max')}
        />
      </div>

      <Field
        label={t('shipping.displayOrder')}
        value={form.display_order}
        onChange={(event) => set('display_order')(event.target.value)}
        inputMode="numeric"
        dir="ltr"
        hint={t('shipping.displayOrderHint')}
        {...errorFor('display_order')}
      />

      <label className="shipping-form__check">
        <input
          type="checkbox"
          checked={form.is_pickup}
          onChange={(event) => set('is_pickup')(event.target.checked)}
        />
        <span>
          {t('shipping.isPickup')}
          <small>{t('shipping.isPickupHint')}</small>
        </span>
      </label>

      {form.is_pickup ? <Alert tone="warning">{t('shipping.isPickupNote')}</Alert> : null}

      <label className="shipping-form__check">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => set('is_active')(event.target.checked)}
        />
        <span>{t('reference.isActive')}</span>
      </label>

      <div className="shipping-form__actions">
        <Button
          onClick={submit}
          loading={save.isPending}
          disabled={!form.name_ar.trim() || (!method && !form.code.trim())}
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
