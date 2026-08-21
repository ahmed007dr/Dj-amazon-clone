import { useTranslation } from 'react-i18next';

import { LOCALES, type Locale } from '@/shared/i18n/config';
import { useDirection } from '@/shared/i18n/useDirection';

import './LanguageSwitch.css';

/**
 * The language switcher.
 *
 * ⚠️  Switching is **instant, with no refetch and no reload**.
 *
 *     The server sends the content in both languages together (ADR-34), so the
 *     translated text is already in memory. Were it to send the translated one
 *     alone, every switch would need every open screen refetched — that is, a
 *     flash and loading screens on a press the user expects to be instantaneous.
 */
export function LanguageSwitch({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const { locale, setLocale } = useDirection();

  return (
    <div className="lang-switch" role="group" aria-label={t('language.label')}>
      {LOCALES.map((code: Locale) => (
        <button
          key={code}
          type="button"
          className={`lang-switch__option ${code === locale ? 'is-active' : ''}`}
          aria-pressed={code === locale}
          aria-label={t('language.switchTo', { name: t(`language.${code}`) })}
          onClick={() => {
            setLocale(code);
          }}
        >
          {compact ? code.toUpperCase() : t(`language.${code}`)}
        </button>
      ))}
    </div>
  );
}
