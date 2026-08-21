import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { confirmPasswordReset } from '@/features/auth/api';
import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AuthPage.css';

/**
 * Setting a new password.
 *
 * ⚠️  The path `/auth/reset-password` matches literally what the server sends in
 *     the email — changing it breaks every link that has actually been sent.
 *
 * ⚠️  And the confirmation uses two fields rather than one.
 *
 *     A typo in a password that cannot be seen locks the account against its
 *     owner, and needs a whole second recovery cycle.
 */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token');

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState('');
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  if (!token) {
    return (
      <div className="container">
        <StateMessage icon="⚠" title={t('auth.missingToken')} body={t('auth.requestNewLink')} />
      </div>
    );
  }

  const mismatch = confirm.length > 0 && password !== confirm;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;

    setError(null);
    setFieldError('');
    setPending(true);

    try {
      await confirmPasswordReset(token as string, password);
      setDone(true);
    } catch (cause) {
      if (isApiError(cause)) {
        setError(cause.displayMessage);
        setFieldError(cause.fieldError('new_password') ?? '');
      } else {
        setError(t('state.errorTitle'));
      }
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <div className="container auth-page">
        <div className="auth-page__card surface">
          <p className="auth-page__icon" aria-hidden>
            ✓
          </p>
          <h1 className="auth-page__title">{t('auth.passwordChanged')}</h1>
          {/* ⚠️  No automatic sign-in: changing the password invalidates every
              session, and signing in by hand confirms the new one really works */}
          <Button block onClick={() => void navigate('/login')}>
            {t('auth.signIn')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container auth-page">
      <form
        className="auth-page__card surface"
        onSubmit={(event) => void handleSubmit(event)}
        noValidate
      >
        <h1 className="auth-page__title">{t('auth.setNewPassword')}</h1>

        {error ? <Alert tone="danger">{error}</Alert> : null}

        <Field
          label={t('auth.newPassword')}
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          hint={t('auth.passwordHint')}
          error={fieldError || undefined}
          onChange={(event) => {
            setPassword(event.target.value);
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

        <Button type="submit" block loading={pending} disabled={mismatch || !password}>
          {t('common.save')}
        </Button>

        <Link to="/login" className="auth-page__link">
          {t('common.back')}
        </Link>
      </form>
    </div>
  );
}
