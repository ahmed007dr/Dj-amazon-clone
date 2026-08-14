import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { isStudent } from '@/features/auth/permissions';
import { useAuth } from '@/features/auth/useAuth';

import './AccountNav.css';

/**
 * تنقّل بوابة الحساب.
 *
 * ⚠️  «حزم دراستي» تظهر **للطلاب وحدهم**.
 *
 *     القسم الذي لا يملكه المستخدم لا يظهر في التنقّل ولا تُجلب
 *     بياناته — وإظهاره ثم رفضه عند الضغط تجربة سيئة، وإخفاؤه
 *     ليس أمنًا: الخادم يرفض بصرف النظر.
 */
export function AccountNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();

  const links = [
    { to: '/account', key: 'account.profile', end: true },
    { to: '/account/orders', key: 'nav.orders' },
    { to: '/account/addresses', key: 'account.addresses' },
    { to: '/account/documents', key: 'account.documents' },
    ...(isStudent(user) ? [{ to: '/account/bundles', key: 'nav.bundles' }] : []),
    { to: '/account/security', key: 'account.security' },
  ];

  return (
    <nav className="account-nav">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end ?? false}
          className={({ isActive }) => `account-nav__link ${isActive ? 'is-active' : ''}`}
          onClick={onNavigate}
        >
          {t(link.key)}
        </NavLink>
      ))}
    </nav>
  );
}
