import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import './StoreNav.css';

const LINKS = [
  { to: '/', key: 'nav.home', end: true },
  { to: '/products', key: 'nav.catalog' },
  // ⚠️  Brands are an independent browsing entry point rather than a filter inside
  //     the catalogue: a medicine buyer searches by the brand they know before they know its category.
  { to: '/brands', key: 'nav.brands' },
  { to: '/bundles', key: 'nav.bundles' },
];

/**
 * The store's navigation links.
 *
 * ⚠️  A standalone component called by both the header and the drawer — **a
 *     single source** for the links. Two separate lists mean a link added to one
 *     and forgotten in the other.
 */
export function StoreNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();

  return (
    <nav className="store-nav">
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end ?? false}
          className={({ isActive }) => `store-nav__link ${isActive ? 'is-active' : ''}`}
          onClick={onNavigate}
        >
          {t(link.key)}
        </NavLink>
      ))}
    </nav>
  );
}
