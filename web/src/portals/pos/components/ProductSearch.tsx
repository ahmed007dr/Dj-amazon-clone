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
 * بحث الأصناف على الكاونتر.
 *
 * ⚠️  **`Enter` يضيف النتيجة الأولى ويفرّغ الحقل.**
 *
 *     الماسح الضوئي يعمل كلوحة مفاتيح: يكتب الباركود ثم يرسل
 *     `Enter`. بلا هذا السلوك يمسح الكاشير الصنف فيظهر في القائمة
 *     ولا يُضاف — فيمدّ يده إلى الشاشة عند كل صنف، وهو ما تلغيه
 *     نقطة البيع أصلًا.
 *
 * ⚠️  والتركيز يعود إلى الحقل بعد كل إضافة.
 *
 *     ضياعه يجعل المسحة التالية تذهب إلى العدم بلا أي مؤشّر —
 *     أسوأ من خطأ ظاهر لأن الكاشير يمسح ثلاث مرات قبل أن ينتبه.
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
        // ⚠️  التركيز التلقائي عند فتح الشاشة: أول ما يفعله الكاشير
        //     هو المسح، ومطالبته بنقرة قبله تكلّف ثانية في كل بيعة.
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
