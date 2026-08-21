import { useTranslation } from 'react-i18next';

import { BrandLogo } from '@/shared/branding/BrandLogo';

import './PosLogo.css';

/**
 * The point-of-sale logo.
 *
 * ⚠️  **Not clickable — unlike the store and admin logos.**
 *
 *     At the counter the logo sits at the top of the screen and the cashier's
 *     finger passes over it dozens of times an hour. Making it a link to the
 *     home page means leaving a half-built sale with an incidental touch — and
 *     rebuilding it in front of the customer. Leaving happens from the account
 *     menu deliberately, not by accident.
 */
export function PosLogo() {
  const { t } = useTranslation();

  return (
    <div className="pos-logo">
      <BrandLogo size="sm" />
      <span className="pos-logo__badge">{t('portal.pos')}</span>
    </div>
  );
}
