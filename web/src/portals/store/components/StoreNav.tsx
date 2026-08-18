import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import './StoreNav.css';

const LINKS = [
  { to: '/', key: 'nav.home', end: true },
  { to: '/products', key: 'nav.catalog' },
  // ⚠️  الماركات مدخل تصفّح مستقل لا فلتر داخل الكتالوج: مشتري
  //     الدواء يبحث باسم الماركة التي يعرفها قبل أن يعرف فئتها.
  { to: '/brands', key: 'nav.brands' },
  { to: '/bundles', key: 'nav.bundles' },
];

/**
 * روابط تنقّل المتجر.
 *
 * ⚠️  مكوّن مستقل يستدعيه الهيدر والـ Drawer معًا — **مصدر واحد**
 *     للروابط. قائمتان منفصلتان تعني رابطًا يُضاف لإحداهما ويُنسى
 *     في الأخرى.
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
