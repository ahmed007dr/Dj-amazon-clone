import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import './PosTabs.css';

/**
 * تنقّل نقطة البيع — شاشتان لا أكثر.
 *
 * ⚠️  **شريط جانبي هنا خطأ.**
 *
 *     الأدمن يتنقّل بين عشر شاشات فيستحق شريطًا؛ والكاشير يعيش في
 *     شاشة واحدة ويزور الثانية مرتين في اليوم. شريط جانبي يأكل
 *     ربع عرض التابلت من قائمة الأصناف مقابل رابطين.
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
