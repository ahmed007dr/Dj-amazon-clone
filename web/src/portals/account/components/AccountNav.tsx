import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { isStudent, isTrade } from '@/features/auth/permissions';
import { useAuth } from '@/features/auth/useAuth';
import { useMyLoyalty } from '@/features/loyalty/api';

import './AccountNav.css';

/**
 * Account portal navigation.
 *
 * ⚠️  "My study bundles" appears **to students alone**.
 *
 *     A section the user does not have appears in neither the navigation nor
 *     the data fetching — showing it and then refusing on click is a bad
 *     experience, and hiding it is not security: the server refuses regardless.
 */
export function AccountNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const loyalty = useMyLoyalty();

  const links = [
    { to: '/account', key: 'account.profile', end: true },
    { to: '/account/orders', key: 'nav.orders' },
    { to: '/account/addresses', key: 'account.addresses' },
    { to: '/account/documents', key: 'account.documents' },
    ...(isStudent(user)
      ? [
          { to: '/account/academic', key: 'academic.profile' },
          { to: '/account/bundles', key: 'nav.bundles' },
        ]
      : []),
    // ⚠️  "My business account" is for business accounts alone.
    //
    //     The link for a non-business account leads to a screen saying "no business
    //     profile" — a correct message, but there is no point showing it to a
    //     retail customer who will never have one.
    ...(isTrade(user) ? [{ to: '/account/trade', key: 'b2b.title' }] : []),
    // ⚠️  "My points" appears to anyone a programme covers **or who has points history**.
    //
    //     Showing it always led a customer outside the targeting to an
    //     "unavailable" screen for no reason they understand — and hiding it
    //     absolutely hid an existing balance from its owner the moment the programme was disabled.
    ...(loyalty.data?.enabled ? [{ to: '/account/loyalty', key: 'loyalty.myPoints' }] : []),
    { to: '/account/notifications', key: 'notifications.title' },
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
