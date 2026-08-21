import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listAdminProducts, type AdminProduct } from '@/features/catalog/adminApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';

import './ProductPicker.css';

/**
 * Choosing a product by search.
 *
 * ⚠️  **A search, not a dropdown.**
 *
 *     A `<select>` of every product means loading the whole catalogue every
 *     time the form opens, and scrolling through thousands of options to find
 *     one item. And the catalogue grows, so the list gets worse over time while
 *     the search does not change.
 *
 * ⚠️  And **the code and the barcode match exactly** — they pass to the server as they are.
 *
 *     The warehouse keeper holds the scanner up to the box, so the complete
 *     number arrives and must give the single item rather than a list to choose from.
 *
 * ⚠️  And the selection **stays visible** after being chosen rather than being
 *     replaced by an empty box.
 *
 *     An adjustment form that does not name the chosen item makes the admin
 *     type the quantity unsure they picked the right row.
 */
export function ProductPicker({
  value,
  onChange,
  error,
}: {
  value: AdminProduct | null;
  onChange: (product: AdminProduct | null) => void;
  error?: string;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();

  const [term, setTerm] = useState('');
  const debounced = useDebounced(term);

  const query = useQuery({
    queryKey: ['admin', 'products', 'picker', debounced],
    queryFn: () => listAdminProducts({ search: debounced, is_active: 'true' }),
    // ⚠️  At least two characters: one character returns half the catalogue for nothing.
    enabled: debounced.trim().length >= 2,
    staleTime: 60 * 1000,
  });

  if (value !== null) {
    return (
      <div className="product-picker">
        <span className="product-picker__label">{t('catalog.product')}</span>
        <div className="product-picker__chosen">
          <span>
            <code>{value.sku}</code> — {localized(value, 'name')}
          </span>
          <button
            type="button"
            className="product-picker__clear"
            onClick={() => {
              onChange(null);
              setTerm('');
            }}
          >
            {t('common.edit')}
          </button>
        </div>
      </div>
    );
  }

  const results = query.data?.results ?? [];
  const searched = debounced.trim().length >= 2;

  return (
    <div className="product-picker">
      <label className="product-picker__label" htmlFor="product-picker-input">
        {t('catalog.product')}
        <em aria-hidden> *</em>
      </label>

      <input
        id="product-picker-input"
        className={`product-picker__input ${error ? 'has-error' : ''}`}
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={t('inventory.pickerPlaceholder')}
        autoComplete="off"
        aria-invalid={error ? true : undefined}
      />

      {query.isFetching ? <Spinner /> : null}

      {searched && !query.isFetching ? (
        results.length === 0 ? (
          <p className="product-picker__empty">{t('inventory.pickerEmpty')}</p>
        ) : (
          <ul className="product-picker__results">
            {results.slice(0, 8).map((product) => (
              <li key={product.id}>
                <button type="button" onClick={() => onChange(product)}>
                  <code>{product.sku}</code>
                  <span>{localized(product, 'name')}</span>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}

      {error ? (
        <p className="product-picker__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
