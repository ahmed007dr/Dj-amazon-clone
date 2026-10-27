import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminStaff,
  useCreateStaff,
  useEmployeeRoles,
  type CreateStaffInput,
  type StaffAccess,
} from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { Spinner } from '@/shared/ui/Spinner';
import { Switch } from '@/shared/ui/Switch';
import { useToast } from '@/shared/ui/useToast';

import './PricingForms.css';
import './CreateStaffForm.css';

const ACCESS_OPTIONS: StaffAccess[] = ['STAFF_PORTAL', 'ADMIN_PANEL'];

/**
 * Adding a staff member.
 *
 * ⚠️  **The person chooses their own password — the admin never sees or sets it.**
 *
 *     Saving sends an invitation email whose link opens the normal "set a password"
 *     page. The temporary-password switch is the fallback for when mail is not set
 *     up yet: it creates a working login immediately and sends nothing, so the
 *     admin has to hand the password over themselves — which is why it is off by
 *     default and says so.
 *
 * ⚠️  **The access type decides the door, the role decides what is behind it.**
 *
 *     "Admin panel" does not make anyone an administrator of everything: they see
 *     only the screens their role's permissions open.
 *
 * ⚠️  Server errors land under the field they belong to (a duplicate email under
 *     the email box), not only in a toast that disappears.
 */
export function CreateStaffForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { notify } = useToast();

  const roles = useEmployeeRoles();
  // ⚠️  Everyone at once, active only: a manager picker that paginates is unusable.
  const managers = useAdminStaff({ active: 'true', limit: 200 });
  const create = useCreateStaff();

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    role: '',
    access: 'STAFF_PORTAL' as StaffAccess,
    manager: '',
    phone_extension: '',
    preferred_language: 'ar' as 'ar' | 'en',
  });
  const [usePassword, setUsePassword] = useState(false);
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  if (roles.isPending) return <Spinner />;

  const activeRoles = (roles.data ?? []).filter((role) => role.is_active);

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    // Typing again clears that field's server error.
    setFieldErrors((current) => (current[key] ? { ...current, [key]: '' } : current));
  };

  const canSubmit =
    form.first_name.trim() !== '' &&
    form.email.trim() !== '' &&
    form.role !== '' &&
    (!usePassword || password !== '');

  const submit = () => {
    setFieldErrors({});
    setFormError(null);

    const body: CreateStaffInput = {
      email: form.email.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      access: form.access,
      role: form.role,
      phone_extension: form.phone_extension.trim(),
      preferred_language: form.preferred_language,
      ...(form.manager ? { manager: form.manager } : {}),
      ...(usePassword ? { temporary_password: password } : {}),
    };

    create.mutate(body, {
      onSuccess: (created) => {
        notify(
          created.invite_sent
            ? t('staff.inviteSent', { email: created.email })
            : t('staff.createdWithPassword', { email: created.email }),
          'success',
        );
        onDone();
      },
      onError: (error) => {
        if (isApiError(error)) {
          const next: Record<string, string> = {};
          for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
          setFieldErrors(next);
          // A field-level error is shown under its field; only an unattached one needs the banner.
          if (Object.keys(next).length === 0) setFormError(error.displayMessage);
          return;
        }
        setFormError(t('state.errorTitle'));
      },
    });
  };

  const err = (key: string) => (fieldErrors[key] ? { error: fieldErrors[key] } : {});

  return (
    <div className="pricing-form">
      {formError ? <Alert tone="danger">{formError}</Alert> : null}

      <div className="pricing-form__row">
        <Field
          label={t('staff.firstName')}
          value={form.first_name}
          onChange={(event) => set('first_name', event.target.value)}
          autoComplete="off"
          required
          {...err('first_name')}
        />
        <Field
          label={t('staff.lastName')}
          value={form.last_name}
          onChange={(event) => set('last_name', event.target.value)}
          autoComplete="off"
          {...err('last_name')}
        />
      </div>

      <Field
        label={t('staff.email')}
        type="email"
        value={form.email}
        onChange={(event) => set('email', event.target.value)}
        autoComplete="off"
        dir="ltr"
        required
        hint={t('staff.emailHint')}
        {...err('email')}
      />

      <div className="pricing-form__row">
        <Field
          label={t('staff.phone')}
          type="tel"
          value={form.phone}
          onChange={(event) => set('phone', event.target.value)}
          autoComplete="off"
          dir="ltr"
          {...err('phone')}
        />
        <Field
          label={t('staff.extension')}
          value={form.phone_extension}
          onChange={(event) => set('phone_extension', event.target.value)}
          dir="ltr"
          {...err('phone_extension')}
        />
      </div>

      <label className="pricing-form__select">
        <span>{t('staff.role')} *</span>
        <select value={form.role} onChange={(event) => set('role', event.target.value)}>
          <option value="">{t('common.choose')}</option>
          {activeRoles.map((role) => (
            <option key={role.id} value={role.id}>
              {localized(role, 'name')}
            </option>
          ))}
        </select>
        {fieldErrors.role ? <span className="pricing-form__error">{fieldErrors.role}</span> : null}
      </label>

      <fieldset className="staff-access">
        <legend>{t('staff.accessType')}</legend>
        {ACCESS_OPTIONS.map((option) => (
          <label
            key={option}
            className={`staff-access__option ${form.access === option ? 'is-selected' : ''}`}
          >
            <input
              type="radio"
              name="staff-access"
              checked={form.access === option}
              onChange={() => set('access', option)}
            />
            <span>
              <strong>{t(`staff.access.${option}`)}</strong>
              <span className="muted">{t(`staff.access.${option}Hint`)}</span>
            </span>
          </label>
        ))}
        {fieldErrors.access ? (
          <span className="pricing-form__error">{fieldErrors.access}</span>
        ) : null}
      </fieldset>

      <label className="pricing-form__select">
        <span>{t('staff.manager')}</span>
        <select value={form.manager} onChange={(event) => set('manager', event.target.value)}>
          <option value="">{t('common.none')}</option>
          {(managers.data?.results ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {row.full_name} · {row.employee_number}
            </option>
          ))}
        </select>
        {fieldErrors.manager ? (
          <span className="pricing-form__error">{fieldErrors.manager}</span>
        ) : null}
      </label>

      <label className="pricing-form__select">
        <span>{t('staff.inviteLanguage')}</span>
        <select
          value={form.preferred_language}
          onChange={(event) => set('preferred_language', event.target.value as 'ar' | 'en')}
        >
          <option value="ar">{t('language.ar')}</option>
          <option value="en">{t('language.en')}</option>
        </select>
      </label>

      <Switch
        checked={usePassword}
        onChange={(next) => {
          setUsePassword(next);
          if (!next) setPassword('');
        }}
        label={t('staff.useTempPassword')}
        description={t('staff.useTempPasswordHint')}
      />

      {usePassword ? (
        <>
          <Alert tone="warning">{t('staff.tempPasswordWarning')}</Alert>
          <Field
            label={t('staff.tempPassword')}
            type="password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setFieldErrors((current) => ({ ...current, temporary_password: '' }));
            }}
            autoComplete="new-password"
            required
            {...err('temporary_password')}
          />
        </>
      ) : (
        <p className="staff-invite-note">{t('staff.inviteNote')}</p>
      )}

      <div className="pricing-form__actions">
        <Button onClick={submit} loading={create.isPending} disabled={!canSubmit}>
          {usePassword ? t('staff.createStaff') : t('staff.createAndInvite')}
        </Button>
        <Button variant="ghost" onClick={onDone} disabled={create.isPending}>
          {t('common.cancel')}
        </Button>
      </div>
    </div>
  );
}
