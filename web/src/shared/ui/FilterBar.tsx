import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import './FilterBar.css';

/**
 * The filter bar.
 *
 * ⚠️  **Filtering always happens on the server.**
 *
 *     Loading every row and then filtering it in the browser works on twenty
 *     rows and stops working on two thousand — and the difference never shows in
 *     the development environment, because its data is sparse.
 */
export function FilterBar({
  children,
  onClear,
  hasFilters = false,
}: {
  children: ReactNode;
  onClear?: () => void;
  hasFilters?: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="filter-bar">
      {children}

      {hasFilters && onClear ? (
        <button type="button" className="filter-bar__clear" onClick={onClear}>
          {t('common.clearFilters')}
        </button>
      ) : null}
    </div>
  );
}

/** A shared search field inside the bar. */
export function FilterSearch({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  const { t } = useTranslation();

  return (
    <input
      type="search"
      className="filter-bar__input"
      value={value}
      placeholder={placeholder ?? t('common.search')}
      aria-label={t('common.search')}
      onChange={(event) => {
        onChange(event.target.value);
      }}
    />
  );
}

/** A shared select inside the bar. */
export function FilterSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
  label: string;
}) {
  return (
    <select
      className="filter-bar__select"
      value={value}
      aria-label={label}
      onChange={(event) => {
        onChange(event.target.value);
      }}
    >
      <option value="">{label}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
