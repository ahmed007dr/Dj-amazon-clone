import { useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';

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

  // ⚠️  Wait before judging: showing the login form to a user whose session is valid
  //     and then hiding it a fraction of a second later looks like a fault.
  if (isRestoring) return <Spinner />;

  const from = (location.state as { from?: string } | null)?.from;

  if (isAuthenticated) return <Navigate to={from ?? '/'} replace />;

  return (
    <div className="container login-page">
      <div className="login-page__card surface">
        <h1 className="login-page__title">{t('auth.signInTo', { name })}</h1>
        <LoginForm
          onSuccess={() => {
            // Return to whatever they were trying to open rather than to the home page
            void navigate(from ?? '/', { replace: true });
          }}
        />

        <div className="login-page__links">
          <Link to="/auth/forgot-password">{t('auth.forgotPassword')}</Link>
          <span className="muted">
            {t('auth.noAccount')} <Link to="/register">{t('auth.createAccount')}</Link>
          </span>
        </div>
      </div>
    </div>
  );
}
