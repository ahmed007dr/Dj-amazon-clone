import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import type { CustomerAddress } from '../types';
import { GOVERNORATES } from '../governorates';
import { useCreateAddress, useUpdateAddress } from '../hooks';

import './AddressForm.css';

/**
 * إضافة عنوان أو تعديله.
 *
 * ⚠️  المحافظة **قائمة مغلقة لا حقل نصي حر**.
 *
 *     رسوم الشحن تُحسب بمطابقة اسم المحافظة حرفيًا مع مناطق
 *     الشحن. «الجيزه» أو «الجيزة ' مسافة» تسقط إلى المنطقة
 *     الافتراضية (٩٠ ج.م) بدل منطقتها الصحيحة (٣٠) — والعميل
 *     يدفع الفرق بلا أن يعرف.
 */
export function AddressForm({
  address,
  onDone,
}: {
  address?: CustomerAddress | undefined;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const createAddress = useCreateAddress();
  const updateAddress = useUpdateAddress();

  const [form, setForm] = useState({
    label: address?.label ?? '',
    recipient_name: address?.recipient_name ?? '',
    phone: address?.phone ?? '',
    governorate: address?.governorate ?? '',
    city: address?.city ?? '',
    street: address?.street ?? '',
    building: address?.building ?? '',
    landmark: address?.landmark ?? '',
    is_default: address?.is_default ?? false,
  });
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof typeof form, value: string | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const onError = (cause: unknown) => {
      setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
    };

    if (address) {
      updateAddress.mutate({ id: address.id, body: form }, { onSuccess: onDone, onError });
      return;
    }

    createAddress.mutate(form, { onSuccess: onDone, onError });
  }

  const pending = createAddress.isPending || updateAddress.isPending;

  return (
    <form className="address-form" onSubmit={handleSubmit} noValidate>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="address-form__grid">
        <Field
          label={t('account.recipientName')}
          required
          value={form.recipient_name}
          autoComplete="name"
          onChange={(event) => {
            set('recipient_name', event.target.value);
          }}
        />
        <Field
          label={t('auth.phone')}
          type="tel"
          required
          value={form.phone}
          autoComplete="tel"
          onChange={(event) => {
            set('phone', event.target.value);
          }}
        />
      </div>

      <div className="address-form__field">
        <label className="address-form__label" htmlFor="governorate">
          {t('account.governorate')}
        </label>
        <select
          id="governorate"
          className="address-form__select"
          required
          value={form.governorate}
          onChange={(event) => {
            set('governorate', event.target.value);
          }}
        >
          <option value="">{t('account.pickGovernorate')}</option>
          {GOVERNORATES.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="address-form__grid">
        <Field
          label={t('account.city')}
          required
          value={form.city}
          onChange={(event) => {
            set('city', event.target.value);
          }}
        />
        <Field
          label={t('account.label')}
          hint={t('account.labelHint')}
          value={form.label}
          onChange={(event) => {
            set('label', event.target.value);
          }}
        />
      </div>

      <Field
        label={t('account.street')}
        required
        value={form.street}
        autoComplete="street-address"
        onChange={(event) => {
          set('street', event.target.value);
        }}
      />

      <div className="address-form__grid">
        <Field
          label={t('account.building')}
          value={form.building}
          onChange={(event) => {
            set('building', event.target.value);
          }}
        />
        <Field
          label={t('account.landmark')}
          hint={t('account.landmarkHint')}
          value={form.landmark}
          onChange={(event) => {
            set('landmark', event.target.value);
          }}
        />
      </div>

      <label className="address-form__check">
        <input
          type="checkbox"
          checked={form.is_default}
          onChange={(event) => {
            set('is_default', event.target.checked);
          }}
        />
        {t('account.makeDefault')}
      </label>

      <div className="address-form__actions">
        <Button type="submit" loading={pending}>
          {t('common.save')}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone} disabled={pending}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}
