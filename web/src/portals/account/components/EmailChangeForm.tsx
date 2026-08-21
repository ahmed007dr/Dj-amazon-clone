import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { requestEmailChange } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

/**
 * Requesting an email change.
 *
 * ⚠️  **Two steps, not one**: a request here, then confirmation through a link
 *     sent to **the new address**. A single step allows an account to be moved
 *     to an email its owner does not control — the fastest route to stealing an
 *     account from an open session.
 *
 * ⚠️  And **the password is required** for the same reason: an unattended
 *     unlocked device is enough to change the email and then take over through
 *     "forgot password".
 */
export function EmailChangeForm() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  const request = useMutation({
    mutationFn: () => requestEmailChange(email, password),
    onSuccess: () => {
      setSent(true);
      setEmail('');
      setPassword('');
      setFieldErrors({});
    },
    onError: (error) => {
      if (isApiError(error)) {
        const next: Record<string, string> = {};
        for (const key of Object.keys(error.fields)) next[key] = error.fieldError(key) ?? '';
        setFieldErrors(next);
      }
    },
  });

  if (sent) {
    // ⚠️  The message names **the new address**, not the old one: the user may
    //     have mistyped it, and naming it is what makes them notice.
    return <Alert tone="success">{t('account.emailChangeSent')}</Alert>;
  }

  return (
    <>
      <p className="muted">{t('account.currentEmail', { email: user?.email ?? '' })}</p>

      <Field
        label={t('account.newEmail')}
        type="email"
        dir="ltr"
        autoComplete="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        {...(fieldErrors.new_email ? { error: fieldErrors.new_email } : {})}
      />

      <Field
        label={t('auth.currentPassword')}
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        hint={t('account.emailChangeWhyPassword')}
        {...(fieldErrors.current_password ? { error: fieldErrors.current_password } : {})}
      />

      <Button
        loading={request.isPending}
        disabled={!email || !password}
        onClick={() => request.mutate()}
      >
        {t('account.sendEmailChange')}
      </Button>
    </>
  );
}
