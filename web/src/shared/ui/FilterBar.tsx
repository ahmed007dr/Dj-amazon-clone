import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import './FilterBar.css';

/**
 * شريط الفلاتر.
 *
 * ⚠️  **الفلترة من الخادم دائمًا.**
 *
 *     تحميل كل الصفوف ثم ترشيحها في المتصفح يعمل على عشرين صفًّا
 *     ويتوقّف عن العمل على ألفين — والفرق لا يظهر في بيئة التطوير
 *     أبدًا لأن بياناتها قليلة.
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

/** حقل بحث موحّد داخل الشريط. */
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

/** قائمة اختيار موحّدة داخل الشريط. */
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
