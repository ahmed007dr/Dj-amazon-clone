import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './AdminLogo.css';

/**
 * The admin panel logo.
 *
 * ⚠️  Smaller than the store logo, and with the portal's label beside it.
 *
 *     The admin may have the store and their panel open in two tabs; and an
 *     identical logo makes them edit a product believing they are browsing, or
 *     hunt for a button that does not exist. The label settles which tab they
 *     are on in half a second.
 */
export function AdminLogo() {
  const { t } = useTranslation();

  return (
    <Link to="/admin" className="admin-logo">
      <BrandLogo size="sm" />
      <span className="admin-logo__badge">{t('portal.admin')}</span>
    </Link>
  );
}
