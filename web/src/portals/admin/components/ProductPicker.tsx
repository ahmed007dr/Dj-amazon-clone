import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listAdminProducts, type AdminProduct } from '@/features/catalog/adminApi';
import { useDebounced } from '@/shared/hooks/useDebounced';
import { useLocalized } from '@/shared/i18n/useLocalized';
import { Spinner } from '@/shared/ui/Spinner';

import './ProductPicker.css';

/**
 * اختيار منتج بالبحث.
 *
 * ⚠️  **بحث لا قائمة منسدلة.**
 *
 *     `<select>` بكل المنتجات يعني تحميل الكتالوج كاملًا في كل فتح
 *     للنموذج، وتمريرًا في آلاف الخيارات لإيجاد صنف. والكتالوج
 *     ينمو، فالقائمة تسوء مع الوقت بينما البحث لا يتغيّر.
 *
 * ⚠️  و**الرمز والباركود يطابقان تمامًا** — يمرّان إلى الخادم كما هما.
 *
 *     أمين المخزن يمسك الماسح أمام العبوة، فيصل الرقم كاملًا ويجب
 *     أن يعطي الصنف الواحد لا قائمة يختار منها.
 *
 * ⚠️  والمختار **يبقى ظاهرًا** بعد الاختيار لا يُستبدَل بمربع فارغ.
 *
 *     نموذج تسوية بلا ذكر الصنف المختار يجعل الأدمن يكتب الكمية
 *     وهو غير واثق أنه اختار الصف الصحيح.
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
    // ⚠️  حرفان على الأقل: حرف واحد يعيد نصف الكتالوج بلا فائدة.
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
