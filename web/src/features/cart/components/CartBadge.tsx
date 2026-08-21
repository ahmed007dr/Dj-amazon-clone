import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useCart } from '../hooks';

import './CartBadge.css';

/**
 * The cart icon with its counter.
 *
 * ⚠️  The counter is not shown while it is zero.
 *
 *     "0" reads as a disabled interface element, and its absence reads as an
 *     empty cart — which is the correct meaning.
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
      {/* The count for the screen reader, with no reliance on the visual badge */}
      <span className="visually-hidden">{t('cart.itemCount', { count })}</span>
    </Link>
  );
}
