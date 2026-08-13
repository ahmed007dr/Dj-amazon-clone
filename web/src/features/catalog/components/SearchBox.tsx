import { useTranslation } from 'react-i18next';

import './SearchBox.css';

/**
 * ⚠️  `type="search"` لا `type="text"`.
 *
 *     يعطي زر مسح أصليًا على الهاتف، ولوحة مفاتيح بزر «بحث» بدل
 *     «إدخال» — وكلاهما فرق ملموس على شاشة صغيرة.
 */
export function SearchBox({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="search-box">
      <span className="search-box__icon" aria-hidden>
        ⌕
      </span>
      <input
        type="search"
        className="search-box__input"
        value={value}
        placeholder={t('common.searchPlaceholder')}
        aria-label={t('common.search')}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </div>
  );
}
