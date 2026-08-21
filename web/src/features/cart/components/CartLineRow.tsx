import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { mediaUrl } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { formatMoney } from '@/shared/utils/format';

import { useRemoveLine, useSetLineQuantity } from '../hooks';
import type { CartLine } from '../types';

import { QuantityStepper } from './QuantityStepper';

import './CartLineRow.css';

/**
 * A line in the cart.
 *
 * ⚠️  A quantity of zero = removal.
 *
 *     The server interprets it that way and the frontend does not object:
 *     someone reducing the quantity to zero means to remove it, and forcing
 *     them to hunt for a second button is extra work.
 */
export function CartLineRow({ line }: { line: CartLine }) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const setQuantity = useSetLineQuantity();
  const removeLine = useRemoveLine();

  const name = localized(line, 'product_name');
  const image = mediaUrl(line.image);
  const pending = setQuantity.isPending || removeLine.isPending;

  return (
    <article className={`cart-line ${pending ? 'is-pending' : ''}`}>
      <Link to={`/products/${line.product_slug}`} className="cart-line__media">
        {image ? (
          <img src={image} alt={name} loading="lazy" />
        ) : (
          <span aria-hidden>⚕</span>
        )}
      </Link>

      <div className="cart-line__info">
        <Link to={`/products/${line.product_slug}`} className="cart-line__name clamp-2">
          {name}
        </Link>
        <p className="cart-line__sku muted">{line.product_sku}</p>

        {/* ⚠️  The pre-discount price appears only when there is a real discount —
            striking through a price equal to the current one is a visual deception */}
        <p className="cart-line__unit">
          {line.pricing.has_discount ? (
            <s className="muted">{formatMoney(line.pricing.list_price, i18n.language)}</s>
          ) : null}
          <span>{formatMoney(line.pricing.unit_price, i18n.language)}</span>
        </p>
      </div>

      <div className="cart-line__controls">
        <QuantityStepper
          value={line.pricing.quantity}
          disabled={pending || !line.id}
          onChange={(quantity) => {
            if (!line.id) return;
            setQuantity.mutate({ lineId: line.id, quantity });
          }}
        />

        <button
          type="button"
          className="cart-line__remove"
          disabled={pending || !line.id}
          onClick={() => {
            if (line.id) removeLine.mutate(line.id);
          }}
        >
          {t('cart.remove')}
        </button>
      </div>

      <p className="cart-line__total">{formatMoney(line.pricing.total, i18n.language)}</p>
    </article>
  );
}
