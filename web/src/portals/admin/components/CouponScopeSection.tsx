import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useProductFormOptions } from '@/features/catalog/adminApi';
import { ProductMultiPicker } from '@/portals/admin/components/ProductMultiPicker';
import type { ScopeState } from '@/portals/admin/components/couponScope';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Alert } from '@/shared/ui/Alert';

import './CouponScope.css';

type Panel = 'products' | 'categories';

/**
 * "Applies to": every product, or only the ones the admin picks.
 *
 * ⚠️  The owner's wording is "ONE product, SOME products or ALL products" — so there are two
 *     choices, not three: *Selected products* covers one and several alike (a list of one
 *     is still a list). A third "single product" option would be the same picker with a
 *     different label and one more way to get the form wrong.
 *
 * ⚠️  The two choices are real radio inputs, not styled buttons: arrow keys, one tab stop
 *     and the group's name for a screen reader come from the platform.
 *
 * ⚠️  Both pickers stay **mounted** while "Selected" is on (the inactive one only `hidden`):
 *     switching between "Products" and "Categories" keeps the search box and results as
 *     they were. Flipping to "All" and back keeps the chosen chips (they live in the
 *     form's state, see `ScopeState`) though the search box starts empty again.
 *
 * ⚠️  The picker is rendered in a fixed place in the tree — never inside a component
 *     defined in this function's body — so a keystroke re-renders it instead of
 *     remounting it and dropping focus.
 */
export function CouponScopeSection({
  value,
  onChange,
  productsError,
  categoriesError,
  problem,
}: {
  value: ScopeState;
  onChange: (next: ScopeState) => void;
  productsError?: string | undefined;
  categoriesError?: string | undefined;
  /** A local validation message (nothing chosen yet). */
  problem?: string | undefined;
}) {
  const { t } = useTranslation();
  const groupName = useId();
  const [panel, setPanel] = useState<Panel>('products');

  const selected = value.mode === 'selected';

  return (
    <fieldset className="coupon-scope">
      <legend>{t('pricing.scope.title')}</legend>

      <div className="coupon-scope__modes">
        {(['all', 'selected'] as const).map((mode) => (
          <label key={mode} className={value.mode === mode ? 'is-on' : ''}>
            <input
              type="radio"
              name={groupName}
              value={mode}
              checked={value.mode === mode}
              onChange={() => {
                onChange({ ...value, mode });
              }}
            />
            <span>{t(mode === 'all' ? 'pricing.scope.all' : 'pricing.scope.selected')}</span>
          </label>
        ))}
      </div>

      {selected ? (
        <p className="coupon-scope__help">{t('pricing.scope.help')}</p>
      ) : (
        <p className="coupon-scope__help">{t('pricing.scope.helpAll')}</p>
      )}

      {/* ⚠️  Rendered only for "Selected", but the selection lives in the form's state —
          so flipping to "All products" and back restores the same chips. */}
      {selected ? (
        <div className="coupon-scope__body">
          <div className="coupon-scope__panels" role="group" aria-label={t('pricing.scope.title')}>
            <button
              type="button"
              aria-pressed={panel === 'products'}
              onClick={() => {
                setPanel('products');
              }}
            >
              {t('pricing.scope.tabProducts')} ({value.products.length})
            </button>
            <button
              type="button"
              aria-pressed={panel === 'categories'}
              onClick={() => {
                setPanel('categories');
              }}
            >
              {t('pricing.scope.tabCategories')} ({value.categories.length})
            </button>
          </div>

          <div hidden={panel !== 'products'}>
            <ProductMultiPicker
              value={value.products}
              onChange={(products) => {
                onChange({ ...value, products });
              }}
              {...(productsError ? { error: productsError } : {})}
            />
          </div>

          <div hidden={panel !== 'categories'}>
            <CategoryPicker
              value={value.categories}
              onChange={(categories) => {
                onChange({ ...value, categories });
              }}
              error={categoriesError}
            />
          </div>

          {problem ? (
            <p className="coupon-scope__problem" role="alert">
              {problem}
            </p>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  );
}

/** A filterable checkbox list of the catalogue's categories. */
function CategoryPicker({
  value,
  onChange,
  error,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  error?: string | undefined;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const inputId = useId();
  const options = useProductFormOptions();

  const [term, setTerm] = useState('');

  const all = options.data?.categories ?? [];
  const chosen = new Set(value);
  const needle = term.trim().toLowerCase();
  const visible = needle
    ? all.filter((item) =>
        `${item.path_label} ${item.name_ar} ${item.name_en}`.toLowerCase().includes(needle),
      )
    : all;

  // Chosen ids the options no longer list (a removed category) stay visible and removable
  const known = new Set(all.map((item) => item.id));
  const orphans = options.data ? value.filter((id) => !known.has(id)) : [];

  const toggle = (id: string) => {
    onChange(chosen.has(id) ? value.filter((item) => item !== id) : [...value, id]);
  };

  return (
    <div className="mpicker">
      <label className="mpicker__label" htmlFor={inputId}>
        {t('pricing.scope.categorySearch')}
      </label>
      <input
        id={inputId}
        type="search"
        className="mpicker__input"
        value={term}
        onChange={(event) => {
          setTerm(event.target.value);
        }}
        placeholder={t('pricing.scope.categoryPlaceholder')}
        autoComplete="off"
      />

      {options.isError ? <Alert tone="danger">{t('pricing.scope.loadError')}</Alert> : null}
      {options.isPending ? <p className="mpicker__status">{t('state.loading')}</p> : null}

      {orphans.length > 0 ? (
        <ul className="mpicker__results" aria-label={t('pricing.scope.unknownCategories')}>
          {orphans.map((id) => (
            <li key={id} className="is-chosen">
              <label>
                <input
                  type="checkbox"
                  checked
                  onChange={() => {
                    toggle(id);
                  }}
                />
                <span className="mpicker__name">
                  {t('pricing.scope.unknownCategory', { id: id.slice(0, 8) })}
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : null}

      {visible.length > 0 ? (
        <ul className="mpicker__results" aria-label={t('pricing.scope.tabCategories')}>
          {visible.map((item) => {
            const isChosen = chosen.has(item.id);
            return (
              <li key={item.id} className={isChosen ? 'is-chosen' : ''}>
                <label>
                  <input
                    type="checkbox"
                    checked={isChosen}
                    onChange={() => {
                      toggle(item.id);
                    }}
                  />
                  <span className="mpicker__name">{item.path_label || localized(item, 'name')}</span>
                  {isChosen ? <em>{t('pricing.scope.added')}</em> : null}
                </label>
              </li>
            );
          })}
        </ul>
      ) : options.data ? (
        <p className="mpicker__empty">{t('pricing.scope.noResults')}</p>
      ) : null}

      {value.length > 0 ? (
        <button
          type="button"
          className="mpicker__clear coupon-scope__clear"
          onClick={() => {
            onChange([]);
          }}
        >
          {t('pricing.scope.clearAll')} ({value.length})
        </button>
      ) : null}

      {error ? (
        <p className="mpicker__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
