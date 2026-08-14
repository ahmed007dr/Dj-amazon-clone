import { useTranslation } from 'react-i18next';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { LoginForm } from '@/features/auth/components/LoginForm';
import { useAuth } from '@/features/auth/useAuth';
import { useBrand } from '@/shared/branding/useBrand';
import { Spinner } from '@/shared/ui/Spinner';

import './LoginPage.css';

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isRestoring } = useAuth();
  const { name } = useBrand();

  // ⚠️  الانتظار قبل الحكم: عرض نموذج الدخول لمستخدم جلسته صالحة
  //     ثم إخفاؤه بعد جزء من الثانية يبدو عطلًا.
  if (isRestoring) return <Spinner />;

  const from = (location.state as { from?: string } | null)?.from;

  if (isAuthenticated) return <Navigate to={from ?? '/'} replace />;

  return (
    <div className="container login-page">
      <div className="login-page__card surface">
        <h1 className="login-page__title">{t('auth.signInTo', { name })}</h1>
        <LoginForm
          onSuccess={() => {
            // العودة إلى ما كان يحاول فتحه لا إلى الرئيسية
            void navigate(from ?? '/', { replace: true });
          }}
        />
      </div>
    </div>
  );
}
