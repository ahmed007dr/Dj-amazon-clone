import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import { GOVERNORATES } from '../governorates';
import { useCreateAddress } from '../hooks';

import './AddressForm.css';

/**
 * إضافة عنوان.
 *
 * ⚠️  المحافظة **قائمة مغلقة لا حقل نصي حر**.
 *
 *     رسوم الشحن تُحسب بمطابقة اسم المحافظة حرفيًا مع مناطق
 *     الشحن. «الجيزه» أو «الجيزة ' مسافة» تسقط إلى المنطقة
 *     الافتراضية (٩٠ ج.م) بدل منطقتها الصحيحة (٣٠) — والعميل
 *     يدفع الفرق بلا أن يعرف.
 */
export function AddressForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const createAddress = useCreateAddress();

  const [form, setForm] = useState({
    label: '',
    recipient_name: '',
    phone: '',
    governorate: '',
    city: '',
    street: '',
    building: '',
    landmark: '',
    is_default: false,
  });
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof typeof form, value: string | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    createAddress.mutate(form, {
      onSuccess: onDone,
      onError: (cause) => {
        setError(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
      },
    });
  }

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
        <Button type="submit" loading={createAddress.isPending}>
          {t('common.save')}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  );
}
