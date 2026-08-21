import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { isApiError } from '@/shared/http';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import { useAuth } from '../useAuth';

import './LoginForm.css';

/**
 * The login form.
 *
 * ⚠️  The login failure message **does not distinguish** a nonexistent email
 *     from a wrong password.
 *
 *     Distinguishing them turns the screen into an account enumeration tool: an
 *     attacker tries an email and learns from the message alone whether it is
 *     registered. The server keeps the message uniform, and the frontend does
 *     not reconstruct the difference from the error codes.
 */
export function LoginForm({ onSuccess }: { onSuccess?: () => void }) {
  const { t } = useTranslation();
  const { signIn } = useAuth();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);

    try {
      await signIn({ identifier, password });
      onSuccess?.();
    } catch (cause) {
      if (!isApiError(cause)) {
        setError(t('state.errorTitle'));
        return;
      }

      if (cause.isOffline) {
        setError(t('state.offlineBody'));
      } else if (cause.isRateLimited) {
        // ⚠️  A different message from a login failure: the user did not get their
        //     details wrong, they exceeded the limit — the action needed is to wait, not to correct.
        setError(cause.displayMessage);
      } else {
        setError(cause.displayMessage || t('auth.loginFailed'));
        setFieldErrors({
          identifier: cause.fieldError('identifier') ?? '',
          password: cause.fieldError('password') ?? '',
        });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="login-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
      {error ? <Alert tone="danger">{error}</Alert> : null}

      <Field
        label={t('auth.identifier')}
        // ⚠️  `text`, not `email` — the field also accepts a phone number, and `email`
        //     makes the browser reject "01001234567" with a validation that does not apply
        type="text"
        inputMode="email"
        name="identifier"
        value={identifier}
        // Tells the password manager what to fill — without it, it fills the wrong field
        autoComplete="username"
        required
        hint={t('auth.identifierHint')}
        error={fieldErrors.identifier || undefined}
        onChange={(event) => {
          setIdentifier(event.target.value);
        }}
      />

      <Field
        label={t('auth.password')}
        type="password"
        name="password"
        value={password}
        autoComplete="current-password"
        required
        error={fieldErrors.password || undefined}
        onChange={(event) => {
          setPassword(event.target.value);
        }}
      />

      <Button type="submit" block loading={pending}>
        {t('auth.signIn')}
      </Button>
    </form>
  );
}
