import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { GOVERNORATES } from '@/features/customers/governorates';
import { Field } from '@/shared/ui/Field';

import { looksLikeEgyptianMobile, type GuestFormValues } from '../guestForm';

import './GuestCheckoutForm.css';

/**
 * The details a visitor gives in place of an account: who, where, how to reach them.
 *
 * ⚠️  **The governorate is a closed list**, for the reason it is in the address
 *     form: shipping is priced by matching it literally against the zones.
 *
 * ⚠️  **The phone is the field that matters most.** The owner confirms every
 *     guest order by ringing it, and the courier needs it at the door — so it is
 *     asked for as a mobile number, with the reason said under it.
 *
 * ⚠️  The last input is a trap. A person never sees it (it sits off-screen and
 *     out of the tab order); a script that fills in every input fills it too, and
 *     the server then refuses the order.
 */
export function GuestCheckoutForm({
  value,
  onChange,
  errors,
  disabled = false,
}: {
  value: GuestFormValues;
  onChange: (next: GuestFormValues) => void;
  /** Server-side field errors, keyed by field name. */
  errors: Partial<Record<keyof GuestFormValues, string>>;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const governorateId = useId();
  const noteId = useId();

  const set = (key: keyof GuestFormValues) => (next: string) => {
    onChange({ ...value, [key]: next });
  };

  // Shown only after the visitor has typed something — not on an empty form
  const phoneHint =
    value.phone && !looksLikeEgyptianMobile(value.phone) ? t('guest.phoneInvalid') : undefined;

  return (
    <div className="guest-form">
      <div className="guest-form__grid">
        <Field
          label={t('account.recipientName')}
          required
          autoComplete="name"
          value={value.recipient_name}
          error={errors.recipient_name}
          disabled={disabled}
          onChange={(event) => {
            set('recipient_name')(event.target.value);
          }}
        />
        <Field
          label={t('auth.phone')}
          type="tel"
          inputMode="tel"
          required
          autoComplete="tel"
          value={value.phone}
          error={errors.phone ?? phoneHint}
          hint={t('guest.phoneHint')}
          disabled={disabled}
          onChange={(event) => {
            set('phone')(event.target.value);
          }}
        />
      </div>

      <Field
        label={t('auth.email')}
        type="email"
        inputMode="email"
        required
        autoComplete="email"
        value={value.email}
        error={errors.email}
        hint={t('guest.emailHint')}
        disabled={disabled}
        onChange={(event) => {
          set('email')(event.target.value);
        }}
      />

      <div className="guest-form__grid">
        <div className="guest-form__select-field">
          <label className="guest-form__label" htmlFor={governorateId}>
            {t('account.governorate')}
          </label>
          <select
            id={governorateId}
            className={`guest-form__select ${errors.governorate ? 'has-error' : ''}`}
            required
            disabled={disabled}
            value={value.governorate}
            aria-invalid={errors.governorate ? true : undefined}
            onChange={(event) => {
              set('governorate')(event.target.value);
            }}
          >
            <option value="">{t('account.pickGovernorate')}</option>
            {GOVERNORATES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {errors.governorate ? (
            <p className="guest-form__error" role="alert">
              {errors.governorate}
            </p>
          ) : null}
        </div>

        <Field
          label={t('account.city')}
          required
          value={value.city}
          error={errors.city}
          disabled={disabled}
          onChange={(event) => {
            set('city')(event.target.value);
          }}
        />
      </div>

      <Field
        label={t('account.street')}
        required
        autoComplete="street-address"
        value={value.street}
        error={errors.street}
        hint={t('guest.streetHint')}
        disabled={disabled}
        onChange={(event) => {
          set('street')(event.target.value);
        }}
      />

      <div className="guest-form__select-field">
        <label className="guest-form__label" htmlFor={noteId}>
          {t('checkout.note')}
        </label>
        <textarea
          id={noteId}
          className="guest-form__note"
          rows={3}
          maxLength={1000}
          disabled={disabled}
          value={value.customer_note}
          placeholder={t('checkout.notePlaceholder')}
          onChange={(event) => {
            set('customer_note')(event.target.value);
          }}
        />
      </div>

      {/* ⚠️  The honeypot — see the component comment. Not `display: none`: some
          scripts skip hidden inputs; off-screen and unfocusable is invisible to
          a person and ordinary to a bot. */}
      <div className="guest-form__trap" aria-hidden="true">
        <label>
          {t('guest.trapLabel')}
          <input
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={value.website}
            onChange={(event) => {
              set('website')(event.target.value);
            }}
          />
        </label>
      </div>
    </div>
  );
}
