import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import { Alert } from '@/shared/ui/Alert';

import { AccountNav } from './components/AccountNav';

import './AccountShell.css';

/**
 * قشرة بوابة الحساب — داخل قشرة المتجر لا بديلًا عنها.
 *
 * ⚠️  العميل يتنقّل بين حسابه والمتجر باستمرار: هيدر مختلف يجعله
 *     يشعر أنه غادر الموقع، ويفقد السلة من عينه في اللحظة التي
 *     يريد فيها إكمال الشراء.
 */
export function AccountShell() {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div className="container account-shell">
      <aside className="account-shell__side">
        <AccountNav />
      </aside>

      <div className="account-shell__content">
        {/* ⚠️  حالة التوثيق تُعرض في كل شاشات الحساب لا في صفحة واحدة:
            المهني الذي ينتظر المراجعة يرى أسعار التجزئة ويظن أن
            النظام معطّل. */}
        {user?.verification_status === 'PENDING' ? (
          <Alert tone="info">{t('auth.awaitingVerification')}</Alert>
        ) : null}
        {user?.verification_status === 'REJECTED' ? (
          <Alert tone="warning">{t('account.verificationRejected')}</Alert>
        ) : null}

        <Outlet />
      </div>
    </div>
  );
}
