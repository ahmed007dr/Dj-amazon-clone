import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { POSProduct } from '@/features/pos/api';
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
 */
export function ProductSearch({ onPick }: { onPick: (product: POSProduct) => void }) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [term, setTerm] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const debounced = useDebounced(term);
  const query = useProductSearch(debounced);

  const results = query.data ?? [];

  const pick = (product: POSProduct) => {
    onPick(product);
    setTerm('');
    inputRef.current?.focus();
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
        onChange={(event) => setTerm(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          const first = results[0];
          if (first) pick(first);
        }}
      />

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
            <code className="pos-search__sku">{product.sku}</code>
          </button>
        ))}
      </div>
    </section>
  );
}
