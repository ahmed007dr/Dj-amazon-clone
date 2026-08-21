import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { AccountMenu } from '@/features/auth/components/AccountMenu';
import { LanguageSwitch } from '@/shared/ui/LanguageSwitch';
import { ThemeSwitch } from '@/shared/ui/ThemeSwitch';

import { StaffLogo } from './StaffLogo';

import './StaffHeader.css';

const LINKS = [
  { to: '/staff', key: 'staff.dashboard', end: true },
  { to: '/staff/customers', key: 'staff.myCustomers' },
];

/**
 * The staff portal header.
 *
 * ⚠️  Two screens only — so navigation lives in the header rather than a sidebar.
 *
 *     A sidebar eats width that the customer and order tables need in exchange
 *     for two links, and the rep works on a laptop rather than a large screen.
 */
export function StaffHeader() {
  const { t } = useTranslation();

  return (
    <header className="staff-header">
      <StaffLogo />

      <nav className="staff-header__nav">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end ?? false}
            className={({ isActive }) =>
              `staff-header__link ${isActive ? 'is-active' : ''}`
            }
          >
            {t(link.key)}
          </NavLink>
        ))}
      </nav>

      <div className="staff-header__actions">
        <LanguageSwitch compact />
        <ThemeSwitch />
        <AccountMenu />
      </div>
    </header>
  );
}
