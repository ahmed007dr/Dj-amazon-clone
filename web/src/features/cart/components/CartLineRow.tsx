import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { VariantTag } from '@/features/catalog/components/VariantTag';
import { mediaUrl } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { PriceTag } from '@/shared/ui/PriceTag';
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

        {/* ⚠️  The colour the customer chose, beside the name: two lines of the same
            product in different colours must be told apart at a glance. */}
        <VariantTag
          hex={line.color?.hex}
          color={line.color ? localized(line.color, 'name') : null}
          variant={line.variant_id ? localized(line, 'variant_name') : null}
        />

        {/* ⚠️  The "price before discount" comes from the server, which sends it only when it
            is above this line's unit price — striking through a price that is not higher than
            the current one is a visual deception. (The old strike on `list_price` is gone
            with it: `list_price` equals `unit_price` here — the promotion is applied below
            the unit price, in `discount_amount` — so it only ever struck the same number.) */}
        <div className="cart-line__unit">
          <PriceTag
            variant="line"
            price={line.pricing.unit_price}
            compareAt={line.compare_at_price}
            percent={line.discount_percent}
          />
        </div>
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
