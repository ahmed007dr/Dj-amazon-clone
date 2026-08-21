import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { changePassword } from '@/features/auth/api';
import { EmailChangeForm } from '@/portals/account/components/EmailChangeForm';
import { SessionList } from '@/portals/account/components/SessionList';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './SecurityPage.css';

/**
 * Security — changing the password.
 *
 * ⚠️  Changing it **ends every session**, including this one.
 *
 *     Said before the press rather than after: a user who suddenly finds
 *     themselves logged out assumes something broke, and retries with a
 *     password they have started to doubt.
 */
export function SecurityPage() {
  const { t } = useTranslation();
  const { signOut } = useAuth();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;

    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      await changePassword(current, next);
      setDone(true);
      // The sessions were ended on the server — the local cleanup keeps the state consistent
      await signOut();
    } catch (cause) {
      if (isApiError(cause)) {
        setError(cause.displayMessage);
        setFieldErrors({
          current_password: cause.fieldError('current_password') ?? '',
          new_password: cause.fieldError('new_password') ?? '',
        });
      } else {
        setError(t('state.errorTitle'));
      }
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <>
        <PageHeader title={t('account.security')} />
        <Alert tone="success">{t('account.passwordChangedSignOut')}</Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('account.security')} />

      <form className="surface security" onSubmit={(event) => void handleSubmit(event)} noValidate>
        {error ? <Alert tone="danger">{error}</Alert> : null}

        {/* The warning before the press, not after */}
        <Alert tone="warning">{t('account.changePasswordWarning')}</Alert>

        <Field
          label={t('auth.currentPassword')}
          type="password"
          autoComplete="current-password"
          required
          value={current}
          error={fieldErrors.current_password || undefined}
          onChange={(event) => {
            setCurrent(event.target.value);
          }}
        />

        <Field
          label={t('auth.newPassword')}
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={next}
          hint={t('auth.passwordHint')}
          error={fieldErrors.new_password || undefined}
          onChange={(event) => {
            setNext(event.target.value);
          }}
        />

        <Field
          label={t('auth.confirmPassword')}
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          error={mismatch ? t('auth.passwordMismatch') : undefined}
          onChange={(event) => {
            setConfirm(event.target.value);
          }}
        />

        <Button type="submit" loading={pending} disabled={mismatch || !next || !current}>
          {t('auth.changePassword')}
        </Button>
      </form>

      {/* ── Changing the email ─────────────────────── */}
      <section className="security-section">
        <h2 className="security-section__title">{t('account.changeEmail')}</h2>
        <EmailChangeForm />
      </section>

      {/* ── Devices ────────────────────────────────── */}
      <section className="security-section">
        <h2 className="security-section__title">{t('account.devices')}</h2>
        <p className="muted">{t('account.devicesHint')}</p>
        <SessionList />
      </section>
    </>
  );
}
