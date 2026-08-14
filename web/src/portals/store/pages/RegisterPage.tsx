import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate } from 'react-router-dom';

import { resendVerification } from '@/features/auth/api';
import { RegisterForm } from '@/features/auth/components/RegisterForm';
import { useAuth } from '@/features/auth/useAuth';
import { Alert } from '@/shared/ui/Alert';
import { Button } from '@/shared/ui/Button';

import './AuthPage.css';

export function RegisterPage() {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const [registered, setRegistered] = useState<string | null>(null);
  const [resent, setResent] = useState(false);

  if (isAuthenticated) return <Navigate to="/" replace />;

  if (registered) {
    /**
     * ⚠️  شاشة «تفقّد بريدك» لا توجيه صامت إلى المتجر.
     *
     *     الحساب لا يعمل قبل التفعيل؛ توجيهه إلى المتجر يجعله يجرّب
     *     الدخول ويفشل بلا أن يعرف السبب. وزر إعادة الإرسال هنا
     *     لأن أول رسالة تسقط في المهملات كثيرًا.
     */
    return (
      <div className="container auth-page">
        <div className="auth-page__card surface">
          <p className="auth-page__icon" aria-hidden>
            ✉
          </p>
          <h1 className="auth-page__title">{t('auth.checkYourEmail')}</h1>
          <p className="auth-page__body muted">
            {t('auth.verificationSentTo', { email: registered })}
          </p>

          {resent ? <Alert tone="success">{t('auth.verificationResent')}</Alert> : null}

          <Button
            variant="secondary"
            block
            onClick={() => {
              void resendVerification(registered).finally(() => {
                setResent(true);
              });
            }}
          >
            {t('auth.resendVerification')}
          </Button>

          <Link to="/login" className="auth-page__link">
            {t('auth.signIn')}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container auth-page">
      <div className="auth-page__card surface">
        <h1 className="auth-page__title">{t('auth.createAccount')}</h1>
        <RegisterForm onSuccess={setRegistered} />

        <p className="auth-page__foot muted">
          {t('auth.haveAccount')} <Link to="/login">{t('auth.signIn')}</Link>
        </p>
      </div>
    </div>
  );
}
