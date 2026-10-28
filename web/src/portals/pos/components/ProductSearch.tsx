import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ColorSwatch } from '@/features/catalog/components/ColorSwatch';
import type { POSProduct, POSVariant } from '@/features/pos/api';
import { useProductSearch } from '@/features/pos/hooks';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import './ProductSearch.css';

/**
 * Item search at the counter.
 *
 * ⚠️  **`Enter` adds the first result and clears the field.**
 *
 *     The scanner works as a keyboard: it types the barcode then sends `Enter`.
 *     Without this behaviour the cashier scans the item, it appears in the list
 *     and is not added — so they reach for the screen on every item, which is
 *     the very thing a point of sale exists to eliminate.
 *
 * ⚠️  And focus returns to the field after every addition.
 *
 *     Losing it sends the next scan into the void with no indication at all —
 *     worse than a visible error, because the cashier scans three times before
 *     noticing.
 *
 * ⚠️  **A product with colours is not added until a colour is named.**
 *
 *     Scanning a colour's own label names it (`matched_variant`) and adds that exact
 *     colour with no further tap. Scanning or tapping the product itself opens the
 *     colour chooser instead — adding "a scrub top" with no colour is a line the server
 *     refuses at the end of the sale, with the customer waiting.
 */
export function ProductSearch({
  onPick,
}: {
  onPick: (product: POSProduct, variant: POSVariant | null) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [term, setTerm] = useState('');
  // The product whose colour the cashier is choosing
  const [choosing, setChoosing] = useState<POSProduct | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const debounced = useDebounced(term);
  const query = useProductSearch(debounced);

  const results = query.data ?? [];

  const finish = (product: POSProduct, variant: POSVariant | null) => {
    onPick(product, variant);
    setChoosing(null);
    setTerm('');
    inputRef.current?.focus();
  };

  const pick = (product: POSProduct) => {
    if (product.variants.length === 0) {
      finish(product, null);
      return;
    }

    const scanned = product.variants.find((variant) => variant.id === product.matched_variant);
    if (scanned) {
      finish(product, scanned);
      return;
    }

    setChoosing(product);
  };

  return (
    <section className="pos-search">
      <input
        ref={inputRef}
        className="pos-search__input"
        value={term}
        placeholder={t('pos.searchPlaceholder')}
        aria-label={t('pos.searchPlaceholder')}
        // ⚠️  Autofocus when the screen opens: the first thing the cashier does
        //     is scan, and asking for a click first costs a second on every sale.
        autoFocus
        onChange={(event) => {
          setTerm(event.target.value);
          setChoosing(null);
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          const first = results[0];
          if (first) pick(first);
        }}
      />

      {choosing ? (
        <div className="pos-search__variants" role="group" aria-label={t('pos.pickVariant')}>
          <p className="pos-search__variants-title">
            {t('pos.pickVariant')} — <strong>{localized(choosing, 'name')}</strong>
          </p>

          {choosing.variants.map((variant) => {
            const soldOut = variant.available <= 0;
            return (
              <button
                key={variant.id}
                type="button"
                className="pos-search__variant"
                // ⚠️  Out *at this register* is disabled, not hidden: the cashier should
                //     see that the colour exists and is simply not on this shelf.
                disabled={soldOut}
                onClick={() => finish(choosing, variant)}
              >
                {variant.color ? <ColorSwatch hex={variant.color.hex} size="lg" /> : null}
                <span className="pos-search__variant-name">
                  {localized(variant.color ?? variant, 'name')}
                  {variant.color && localized(variant, 'name') !== localized(variant.color, 'name')
                    ? ` · ${localized(variant, 'name')}`
                    : ''}
                </span>
                <span className="pos-search__variant-stock">
                  {soldOut
                    ? t('pos.variantSoldOut')
                    : t('pos.variantAvailable', { count: variant.available })}
                </span>
              </button>
            );
          })}

          <button type="button" className="pos-search__variants-cancel" onClick={() => setChoosing(null)}>
            {t('common.cancel')}
          </button>
        </div>
      ) : null}

      <div className="pos-search__results">
        {query.isFetching && results.length === 0 ? <Spinner /> : null}

        {!query.isFetching && results.length === 0 ? (
          <StateMessage icon="⌕" title={t('pos.noResults')} />
        ) : null}

        {results.map((product) => (
          <button
            key={product.id}
            type="button"
            className="pos-search__item"
            onClick={() => pick(product)}
          >
            <span className="pos-search__name truncate">{localized(product, 'name')}</span>
            {product.variants.length > 0 ? (
              <span className="pos-search__dots" aria-hidden>
                {product.variants
                  .filter((variant) => variant.color)
                  .slice(0, 6)
                  .map((variant) => (
                    <ColorSwatch key={variant.id} hex={variant.color!.hex} size="sm" />
                  ))}
              </span>
            ) : null}
            <code className="pos-search__sku">{product.sku}</code>
          </button>
        ))}
      </div>
    </section>
  );
}
