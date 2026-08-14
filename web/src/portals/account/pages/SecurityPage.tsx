import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { changePassword } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError } from '@/shared/http';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './SecurityPage.css';

/**
 * الأمان — تغيير كلمة المرور.
 *
 * ⚠️  تغييرها **يُنهي كل الجلسات** بما فيها هذه.
 *
 *     قوله قبل الضغط لا بعده: المستخدم الذي يجد نفسه خارج الحساب
 *     فجأة يظن أن شيئًا كُسر، ويعيد المحاولة بكلمة مرور صار
 *     يشكّ فيها.
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
      // الجلسات أُنهيت في الخادم — التنظيف المحلي يجعل الحالة متطابقة
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

        {/* التحذير قبل الضغط لا بعده */}
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
    </>
  );
}
