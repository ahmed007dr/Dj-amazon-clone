import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useCart } from '../hooks';

import './CartBadge.css';

/**
 * أيقونة السلة بعدّادها.
 *
 * ⚠️  العدّاد لا يُعرض وهو صفر.
 *
 *     «٠» تُقرأ كعنصر واجهة معطّل، والغياب يقرأ كسلة فارغة —
 *     وهو المعنى الصحيح.
 */
export function CartBadge() {
  const { t } = useTranslation();
  const { data } = useCart();

  const count = data?.totals.item_count ?? 0;

  return (
    <Link to="/cart" className="cart-badge" aria-label={t('nav.cart')}>
      <span className="cart-badge__icon" aria-hidden>
        ⛿
      </span>
      {count > 0 ? (
        <span className="cart-badge__count" aria-hidden>
          {count > 99 ? '99+' : count}
        </span>
      ) : null}
      {/* العدد للقارئ الشاشي بلا اعتماد على الشارة البصرية */}
      <span className="visually-hidden">{t('cart.itemCount', { count })}</span>
    </Link>
  );
}
