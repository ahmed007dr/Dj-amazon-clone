import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { AddToCartButton } from '@/features/cart/components/AddToCartButton';
import { mediaUrl } from '@/shared/http';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { formatMoney } from '@/shared/utils/format';
import { Badge } from '@/shared/ui/Badge';

import type { Availability, ProductListItem } from '../types';

import { StockBadge } from './StockBadge';

import './ProductCard.css';

/**
 * A product card.
 *
 * ⚠️  The name is chosen from `name_ar`/`name_en` **in memory**.
 *
 *     The server sent both (ADR-34), so switching the language redraws the card
 *     immediately with no network call and no loading skeleton.
 *
 * ⚠️  `availability` arrives from the grid, which fetches the whole page at once.
 *
 *     What has run out is not in this list at all — the server excludes it — so
 *     the badge here is not there to say "unavailable". It is there for the case
 *     between the two: three left. That is the number that decides whether
 *     somebody buys now or next week, and it is the one the card was silent
 *     about while the product page showed it.
 */
export function ProductCard({
  product,
  availability,
}: {
  product: ProductListItem;
  availability?: Availability | undefined;
}) {
  const { t, i18n } = useTranslation();
  const localized = useLocalized();

  const name = localized(product, 'name');

  // ⚠️  The server sends the complete image object rather than its path — and the alt text comes from it
  //     more precise than the product name, because it describes the image, not the item.
  const image = mediaUrl(product.primary_image?.image);
  const imageAlt = product.primary_image
    ? localized(product.primary_image, 'alt_text') || name
    : name;

  return (
    <article className="product-card surface">
      <Link to={`/products/${product.slug}`} className="product-card__media">
        {image ? (
          <img src={image} alt={imageAlt} loading="lazy" decoding="async" />
        ) : (
          <span className="product-card__placeholder" aria-hidden>
            ⚕
          </span>
        )}
        {product.is_featured ? (
          <span className="product-card__flag">
            <Badge tone="info">★</Badge>
          </span>
        ) : null}
      </Link>

      <div className="product-card__body">
        <Link to={`/products/${product.slug}`} className="product-card__name clamp-2">
          {name}
        </Link>

        {product.brand ? (
          <p className="product-card__brand muted truncate">
            {localized(product.brand, 'name')}
          </p>
        ) : null}

        <p className="product-card__price">
          {formatMoney(product.base_price, i18n.language)}
        </p>

        <p className="product-card__sku muted">
          {t('catalog.sku')}: {product.sku}
        </p>

        <StockBadge availability={availability} />

        <div className="product-card__action">
          {/* ⚠️  Disabled on a confirmed zero — not on a missing answer.
              The list should not contain one at all; if stock ran out between the
              page loading and this render, refusing the click here is better than
              an error after it. */}
          <AddToCartButton
            productId={product.id}
            block
            disabled={availability?.is_available === false}
          />
        </div>
      </div>
    </article>
  );
}
