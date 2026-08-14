import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { verifyEmail } from '@/features/auth/api';
import { useAuth } from '@/features/auth/useAuth';
import { isApiError, setAccessToken } from '@/shared/http';
import { Button } from '@/shared/ui/Button';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './AuthPage.css';

type State = 'checking' | 'done' | 'failed';

/**
 * تفعيل البريد.
 *
 * ⚠️  المسار `/auth/verify-email` **يطابق ما يرسله الخادم** في
 *     البريد حرفيًا (`accounts/api.py`). تغييره هنا يكسر كل رابط
 *     أُرسل فعلًا — بما فيها روابط في بُرُد وصلت أمس.
 *
 * ⚠️  والتفعيل يُنفَّذ **مرة واحدة**.
 *
 *     التوكن يُستهلك عند أول استخدام؛ و`StrictMode` في التطوير
 *     يشغّل التأثير مرتين، فبلا حارس تفشل المحاولة الثانية ويرى
 *     المستخدم «رابط غير صالح» بعد تفعيل ناجح.
 */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { isAuthenticated } = useAuth();

  const token = params.get('token');
  const [state, setState] = useState<State>('checking');
  const [message, setMessage] = useState('');
  const attempted = useRef(false);

  useEffect(() => {
    if (!token) {
      setState('failed');
      setMessage(t('auth.missingToken'));
      return;
    }

    if (attempted.current) return;
    attempted.current = true;

    void (async () => {
      try {
        const response = await verifyEmail(token);
        // الجلسة تبدأ فورًا — من ضغط الرابط في بريده أثبت ملكيته
        setAccessToken(response.access);
        setState('done');
      } catch (cause) {
        setState('failed');
        setMessage(isApiError(cause) ? cause.displayMessage : t('state.errorTitle'));
      }
    })();
  }, [token, t]);

  if (state === 'checking') return <Spinner label={t('auth.verifying')} />;

  if (state === 'failed') {
    return (
      <div className="container">
        <StateMessage
          icon="⚠"
          title={t('auth.verificationFailed')}
          body={message}
          action={
            <Button variant="secondary">
              <Link to="/register" className="auth-page__link">
                {t('auth.createAccount')}
              </Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="container auth-page">
      <div className="auth-page__card surface">
        <p className="auth-page__icon" aria-hidden>
          ✓
        </p>
        <h1 className="auth-page__title">{t('auth.verified')}</h1>
        <p className="auth-page__body muted">{t('auth.verifiedBody')}</p>

        <Button
          block
          onClick={() => {
            // ⚠️  إعادة تحميل كاملة: الجلسة بدأت خارج `AuthProvider`
            //     فلا يعرف بها حتى يُعاد إقلاعه.
            window.location.assign(isAuthenticated ? '/' : '/');
            void navigate('/');
          }}
        >
          {t('auth.startShopping')}
        </Button>
      </div>
    </div>
  );
}
