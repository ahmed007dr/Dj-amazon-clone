import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { requestPasswordReset } from '@/features/auth/api';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';
import { Field } from '@/shared/ui/Field';

import './AuthPage.css';

/**
 * طلب استرجاع كلمة المرور.
 *
 * ⚠️  **نفس الرسالة سواء وُجد البريد أو لم يوجد.**
 *
 *     التفريق يحوّل الشاشة إلى أداة تعداد حسابات: يجرّب المهاجم
 *     بريدًا ويعرف من الرد وحده إن كان مسجَّلًا. الخادم يوحّد الرد،
 *     والواجهة لا تُعيد بناء الفرق من رمز الخطأ.
 *
 *     ولذلك النجاح والفشل يعرضان نفس الشاشة هنا عمدًا.
 */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);

    void requestPasswordReset(email)
      .catch(() => {
        // متعمَّد: لا نكشف إن كان البريد مسجَّلًا
      })
      .finally(() => {
        setPending(false);
        setSent(true);
      });
  }

  if (sent) {
    return (
      <div className="container auth-page">
        <div className="auth-page__card surface">
          <p className="auth-page__icon" aria-hidden>
            ✉
          </p>
          <h1 className="auth-page__title">{t('auth.checkYourEmail')}</h1>
          <Alert tone="info">{t('auth.resetSentGeneric')}</Alert>
          <Link to="/login" className="auth-page__link">
            {t('auth.signIn')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container auth-page">
      <form className="auth-page__card surface" onSubmit={handleSubmit} noValidate>
        <h1 className="auth-page__title">{t('auth.forgotPassword')}</h1>
        <p className="auth-page__body muted">{t('auth.forgotPasswordBody')}</p>

        <Field
          label={t('auth.email')}
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />

        <Button type="submit" block loading={pending} disabled={!email.trim()}>
          {t('auth.sendResetLink')}
        </Button>

        <Link to="/login" className="auth-page__link">
          {t('common.back')}
        </Link>
      </form>
    </div>
  );
}
