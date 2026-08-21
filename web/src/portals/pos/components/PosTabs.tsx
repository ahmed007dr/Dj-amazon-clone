import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import './PosTabs.css';

/**
 * Point-of-sale navigation — two screens, no more.
 *
 * ⚠️  **A sidebar here is a mistake.**
 *
 *     The admin moves between ten screens and so deserves a bar; the cashier
 *     lives in one screen and visits the second twice a day. A sidebar eats a
 *     quarter of the tablet's width from the item list in exchange for two links.
 */
export function PosTabs() {
  const { t } = useTranslation();

  return (
    <nav className="pos-tabs">
      <NavLink
        to="/pos"
        end
        className={({ isActive }) => `pos-tabs__link ${isActive ? 'is-active' : ''}`}
      >
        {t('pos.sale')}
      </NavLink>
      <NavLink
        to="/pos/shift"
        className={({ isActive }) => `pos-tabs__link ${isActive ? 'is-active' : ''}`}
      >
        {t('pos.shift')}
      </NavLink>
    </nav>
  );
}
