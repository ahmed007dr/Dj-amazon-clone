import { useTranslation } from 'react-i18next';

import { useLocalized } from '@/shared/i18n/useLocalized';

import { useCategories } from '../hooks';

import './CategoryFilter.css';

/**
 * فلتر الفئات.
 *
 * ⚠️  الفلترة **من الخادم** لا من العميل.
 *
 *     تحميل كل المنتجات ثم ترشيحها في المتصفح يعمل على عشرين منتجًا
 *     ويتوقّف عن العمل على ألفين — والفرق لا يظهر في بيئة التطوير
 *     أبدًا.
 */
export function CategoryFilter({
  value,
  onChange,
}: {
  value: string | undefined;
  onChange: (slug: string | undefined) => void;
}) {
  const { t } = useTranslation();
  const localized = useLocalized();
  const { data: categories = [] } = useCategories();

  return (
    <div className="category-filter">
      <h2 className="category-filter__title">{t('catalog.category')}</h2>

      <ul className="category-filter__list">
        <li>
          <button
            type="button"
            className={`category-filter__item ${!value ? 'is-active' : ''}`}
            onClick={() => {
              onChange(undefined);
            }}
          >
            {t('common.all')}
          </button>
        </li>

        {categories.map((category) => (
          <li key={category.id}>
            <button
              type="button"
              className={`category-filter__item ${value === category.slug ? 'is-active' : ''}`}
              onClick={() => {
                onChange(category.slug);
              }}
            >
              {localized(category, 'name')}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
