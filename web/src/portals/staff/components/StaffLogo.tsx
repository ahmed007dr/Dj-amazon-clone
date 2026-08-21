import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './StaffLogo.css';

/**
 * The staff portal logo.
 *
 * ⚠️  **The badge settles which portal is open.**
 *
 *     The rep may have the store and their portal open in two tabs — browsing as
 *     a customer to see what the customer sees, then creating an order. An
 *     identical logo makes them build the cart in the wrong place.
 */
export function StaffLogo() {
  const { t } = useTranslation();

  return (
    <Link to="/staff" className="staff-logo">
      <BrandLogo size="sm" />
      <span className="staff-logo__badge">{t('portal.staff')}</span>
    </Link>
  );
}
