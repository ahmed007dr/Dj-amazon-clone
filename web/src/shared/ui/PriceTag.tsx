import { useTranslation } from 'react-i18next';

import { formatMoney, formatNumber } from '@/shared/utils/format';

import './PriceTag.css';

export type PriceTagVariant = 'card' | 'detail' | 'line';

export interface PriceTagProps {
  /** The price this customer pays — a money string (ADR-31). */
  price: string;
  /**
   * The "price before discount", exactly as the server sent it.
   *
   * ⚠️  **Rendered when present, never decided here.** The server sends it only while it is
   *     above the price this viewer pays (`catalog/compare_at.py`); this component does not
   *     compare the two, so it can never disagree with the cart about whether a discount exists.
   */
  compareAt?: string | null | undefined;
  /** The saving as a whole percentage, rounded down by the server. Below 1 there is no badge. */
  percent?: number | null | undefined;
  variant?: PriceTagVariant;
  /** Text before the price, e.g. "From" when the options are priced differently. */
  prefix?: string | undefined;
}

/**
 * A price, with its "was" price and the saving when there is one.
 *
 *   card    compact — product grids and search results
 *   detail  large   — the product page, with a "You save …" line
 *   line    small   — a cart row
 *
 * ⚠️  Not colour alone. The old price is struck through **and** muted, the saving is written
 *     out as a badge ("-20%" / "خصم ٢٠٪"), and a visually hidden sentence ("Was EGP 100, now
 *     EGP 80") is what a screen reader gets — the visible pieces are `aria-hidden` so it is
 *     not read twice, and a struck-through number alone is not announced as "old" by most readers.
 *
 * ⚠️  Logical properties only and an isolated badge, so the same markup reads right-to-left:
 *     in Arabic the percentage is written as a word and a number ("خصم ٢٠٪"), not a leading
 *     minus sign that bidi reordering would move to the wrong end.
 */
export function PriceTag({ price, compareAt, percent, variant = 'card', prefix }: PriceTagProps) {
  const { t, i18n } = useTranslation();

  const money = (value: string) => formatMoney(value, i18n.language);
  const was = typeof compareAt === 'string' && compareAt !== '' ? compareAt : null;
  const hasWas = was !== null;
  const showBadge = was !== null && typeof percent === 'number' && percent >= 1;
  const percentText = typeof percent === 'number' ? formatNumber(percent, i18n.language) : '';

  // Display only — the server already settled that `compareAt` is above `price`.
  const saving = was !== null ? Number.parseFloat(was) - Number.parseFloat(price) : 0;

  const spoken =
    was !== null
      ? t('catalog.price.wasNow', { was: money(was), now: money(price) })
      : t('catalog.price.now', { now: money(price) });

  return (
    <div className={`price-tag price-tag--${variant}${hasWas ? ' has-was' : ''}`}>
      <p className="price-tag__row">
        {prefix ? (
          <span className="price-tag__prefix" aria-hidden>
            {prefix}
          </span>
        ) : null}
        <span className="price-tag__now" aria-hidden>
          {money(price)}
        </span>
        {was !== null ? (
          <s className="price-tag__was" aria-hidden>
            {money(was)}
          </s>
        ) : null}
        {showBadge ? (
          <span className="price-tag__badge" aria-hidden>
            {t('catalog.price.badge', { percent: percentText })}
          </span>
        ) : null}
        <span className="visually-hidden">
          {prefix ? `${prefix} ` : ''}
          {spoken}
          {showBadge ? `. ${t('catalog.price.badgeLabel', { percent: percentText })}` : ''}
        </span>
      </p>

      {variant === 'detail' && was !== null && saving > 0 ? (
        <p className="price-tag__save">
          {t('catalog.price.save', { amount: money(saving.toFixed(2)) })}
        </p>
      ) : null}
    </div>
  );
}
