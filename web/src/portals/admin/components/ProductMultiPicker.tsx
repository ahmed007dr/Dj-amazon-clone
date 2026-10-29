import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listAdminProducts } from '@/features/catalog/adminApi';
import {
  NAME_LOOKUP_CAP,
  useResolvedProducts,
  type PickedProduct,
} from '@/features/pricing/scope';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Button } from '@/shared/ui/Button';
import { Pagination } from '@/shared/ui/Pagination';

import './ProductMultiPicker.css';

/**
 * Choosing **several** products by search — for a coupon limited to some of the catalogue.
 *
 * ⚠️  Not the single-select `ProductPicker`: that one swaps itself for the chosen row and
 *     is shaped for "one product per form". This one keeps the search open and collects.
 *
 * ⚠️  **The search input is never remounted.** It sits at the top of one stable tree, and
 *     the results below it change underneath — so typing inside a Drawer cannot lose focus
 *     (the bug the shared Drawer/Modal had). `keepPreviousData` keeps the old rows on
 *     screen while the next page loads instead of flashing an empty list under the cursor.
 *
 * ⚠️  **Ids are the truth, names are labels.** A product already in the selection stays in
 *     it whether or not its name is known (see `PickedProduct`); a chip that cannot be
 *     named (a deleted product, say) is still shown and still removable.
 *
 * ⚠️  Already-chosen rows are checked and greyed, not hidden: hiding them makes the page
 *     shorter after every click and the list jumps under the finger.
 */
export function ProductMultiPicker({
  value,
  onChange,
  error,
  disabled = false,
}: {
  value: PickedProduct[];
  onChange: (next: PickedProduct[]) => void;
  error?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const inputId = useId();
  const errorId = useId();

  const [term, setTerm] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebounced(term).trim();

  const query = useQuery({
    queryKey: ['admin', 'products', 'multi-picker', debounced, page],
    queryFn: () => listAdminProducts({ ...(debounced ? { search: debounced } : {}), page }),
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  });

  const rows = query.data?.results ?? [];
  const chosen = new Set(value.map((item) => item.id));
  const resolved = useResolvedProducts(value);

  const toggle = (product: PickedProduct) => {
    onChange(
      chosen.has(product.id)
        ? value.filter((item) => item.id !== product.id)
        : [
            ...value,
            {
              id: product.id,
              ...(product.sku ? { sku: product.sku } : {}),
              ...(product.name_ar ? { name_ar: product.name_ar } : {}),
              ...(product.name_en ? { name_en: product.name_en } : {}),
            },
          ],
    );
  };

  const addPage = () => {
    const fresh = rows
      .filter((row) => !chosen.has(row.id))
      .map((row) => ({ id: row.id, sku: row.sku, name_ar: row.name_ar, name_en: row.name_en }));
    if (fresh.length > 0) onChange([...value, ...fresh]);
  };

  const unchosenOnPage = rows.filter((row) => !chosen.has(row.id)).length;

  // Chips: every named product, plus the unnamed ones that are being looked up.
  // The rest (a very long scope) are counted, not drawn — they are still saved.
  let unnamedShown = 0;
  let hidden = 0;
  const chips = resolved.filter((item) => {
    if (item.sku) return true;
    unnamedShown += 1;
    if (unnamedShown <= NAME_LOOKUP_CAP) return true;
    hidden += 1;
    return false;
  });

  const label = (item: PickedProduct) => {
    const base = item.sku
      ? localized(item, 'name') || item.sku
      : t('pricing.scope.unnamed', { id: item.id.slice(0, 8) });
    return item.deleted ? `${base} (${t('pricing.scope.deleted')})` : base;
  };

  return (
    <div className="mpicker">
      <label className="mpicker__label" htmlFor={inputId}>
        {t('pricing.scope.searchLabel')}
      </label>
      <input
        id={inputId}
        type="search"
        className={`mpicker__input ${error ? 'has-error' : ''}`}
        value={term}
        onChange={(event) => {
          setTerm(event.target.value);
          setPage(1);
        }}
        placeholder={t('pricing.scope.searchPlaceholder')}
        autoComplete="off"
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />

      <p className="mpicker__status" role="status">
        {query.isError
          ? t('pricing.scope.loadError')
          : query.isPending
            ? t('state.loading')
            : t('pricing.scope.found', { count: query.data?.count ?? 0 })}
      </p>

      {query.isError ? (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            void query.refetch();
          }}
        >
          {t('common.retry')}
        </Button>
      ) : null}

      {rows.length > 0 ? (
        <>
          <ul
            className={`mpicker__results ${query.isPlaceholderData ? 'is-stale' : ''}`}
            aria-label={t('pricing.scope.resultsLabel')}
          >
            {rows.map((product) => {
              const isChosen = chosen.has(product.id);
              return (
                <li key={product.id} className={isChosen ? 'is-chosen' : ''}>
                  <label>
                    <input
                      type="checkbox"
                      checked={isChosen}
                      disabled={disabled}
                      onChange={() => {
                        toggle(product);
                      }}
                    />
                    <code dir="ltr">{product.sku}</code>
                    <span className="mpicker__name">{localized(product, 'name')}</span>
                    {isChosen ? <em>{t('pricing.scope.added')}</em> : null}
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="mpicker__tools">
            <Button
              size="sm"
              variant="ghost"
              disabled={disabled || unchosenOnPage === 0}
              onClick={addPage}
            >
              {t('pricing.scope.addPage')}
            </Button>
          </div>

          {query.data ? (
            <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
          ) : null}
        </>
      ) : !query.isPending && !query.isError ? (
        <p className="mpicker__empty">{t('pricing.scope.noResults')}</p>
      ) : null}

      <div className="mpicker__chosen">
        <div className="mpicker__chosen-head">
          <strong>{t('pricing.scope.chosenTitle', { count: value.length })}</strong>
          {value.length > 0 ? (
            <button
              type="button"
              className="mpicker__clear"
              disabled={disabled}
              onClick={() => {
                onChange([]);
              }}
            >
              {t('pricing.scope.clearAll')}
            </button>
          ) : null}
        </div>

        {value.length === 0 ? (
          <p className="mpicker__empty">{t('pricing.scope.noneChosen')}</p>
        ) : (
          <ul className="mpicker__chips">
            {chips.map((item) => (
              <li key={item.id} className={`mpicker__chip ${item.deleted ? 'is-deleted' : ''}`}>
                {item.sku ? <code dir="ltr">{item.sku}</code> : null}
                <span>{label(item)}</span>
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={t('pricing.scope.remove', { name: label(item) })}
                  onClick={() => {
                    onChange(value.filter((entry) => entry.id !== item.id));
                  }}
                >
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden focusable="false">
                    <path
                      d="M3.5 3.5l9 9m0-9l-9 9"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}

        {hidden > 0 ? (
          <p className="mpicker__empty">{t('pricing.scope.moreKept', { count: hidden })}</p>
        ) : null}
      </div>

      {error ? (
        <p id={errorId} className="mpicker__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
