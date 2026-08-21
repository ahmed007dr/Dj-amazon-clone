import { useTranslation } from 'react-i18next';

import './SearchBox.css';

/**
 * ⚠️  `type="search"`, not `type="text"`.
 *
 *     It gives a native clear button on a phone, and a keyboard with a "search"
 *     key instead of "enter" — both a tangible difference on a small screen.
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
