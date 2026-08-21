import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import * as api from '../api';
import { SELF_SIGNUP_TYPES, type SelfSignupType } from '../types';

import './RegisterForm.css';

/**
 * The registration form.
 *
 * ⚠️  **The account does not work until it is activated by email.**
 *
 *     So success here neither logs the user in nor redirects to the store — it
 *     tells them exactly what to do next. A silent redirect makes them try to
 *     log in and fail with no idea why.
 *
 * ⚠️  And the password constraints come from the server as they are.
 *
 *     Django enforces four validators (length · commonness · similarity to the
 *     email · digits only). Rewriting them here produces two lists that drift
 *     apart, so the user sees "a valid password" and the server then rejects it.
 */
export function RegisterForm({ onSuccess }: { onSuccess: (email: string) => void }) {
  const { t, i18n } = useTranslation();

  const [form, setForm] = useState({
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    phone: '',
    account_type: 'STUDENT' as SelfSignupType,
  });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const set = (key: keyof typeof form) => (value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      await api.register({
        ...form,
        preferred_language: i18n.language.slice(0, 2) === 'en' ? 'en' : 'ar',
      });
      onSuccess(form.email);
    } catch (cause) {
      if (!isApiError(cause)) {
        setError(t('state.errorTitle'));
        return;
      }

      setError(cause.displayMessage);
      setFieldErrors({
        email: cause.fieldError('email') ?? '',
        password: cause.fieldError('password') ?? '',
        phone: cause.fieldError('phone') ?? '',
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="register-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="register-form__row">
        <Field
          label={t('auth.firstName')}
          name="first_name"
          autoComplete="given-name"
          value={form.first_name}
          onChange={(event) => set('first_name')(event.target.value)}
        />
        <Field
          label={t('auth.lastName')}
          name="last_name"
          autoComplete="family-name"
          value={form.last_name}
          onChange={(event) => set('last_name')(event.target.value)}
        />
      </div>

      <Field
        label={t('auth.email')}
        type="email"
        name="email"
        autoComplete="email"
        required
        value={form.email}
        error={fieldErrors.email || undefined}
        onChange={(event) => set('email')(event.target.value)}
      />

      <Field
        label={t('auth.phone')}
        type="tel"
        name="phone"
        autoComplete="tel"
        value={form.phone}
        hint={t('auth.phoneHint')}
        error={fieldErrors.phone || undefined}
        onChange={(event) => set('phone')(event.target.value)}
      />

      <Field
        label={t('auth.password')}
        type="password"
        name="password"
        autoComplete="new-password"
        required
        minLength={8}
        value={form.password}
        hint={t('auth.passwordHint')}
        error={fieldErrors.password || undefined}
        onChange={(event) => set('password')(event.target.value)}
      />

      <div className="register-form__types">
        <span className="register-form__label">{t('auth.accountType')}</span>
        <div className="register-form__options" role="radiogroup">
          {SELF_SIGNUP_TYPES.map((type) => (
            <label
              key={type}
              className={`type-chip ${form.account_type === type ? 'is-selected' : ''}`}
            >
              <input
                type="radio"
                name="account_type"
                value={type}
                checked={form.account_type === type}
                className="visually-hidden"
                onChange={() => set('account_type')(type)}
              />
              {t(`accountType.${type}`)}
            </label>
          ))}
        </div>
        {/* ⚠️  A professional goes through a manual review — saying so now prevents a false expectation */}
        {form.account_type !== 'STUDENT' ? (
          <p className="register-form__note muted">{t('auth.professionalNote')}</p>
        ) : null}
      </div>

      <Button type="submit" block loading={pending}>
        {t('auth.createAccount')}
      </Button>
    </form>
  );
}
