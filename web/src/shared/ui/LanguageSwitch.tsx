import { useTranslation } from 'react-i18next';

import { LOCALES, type Locale } from '@/shared/i18n/config';
import { useDirection } from '@/shared/i18n/useDirection';

import './LanguageSwitch.css';

/**
 * مبدّل اللغة.
 *
 * ⚠️  التبديل **فوري بلا إعادة جلب ولا إعادة تحميل**.
 *
 *     الخادم يرسل المحتوى باللغتين معًا (ADR-34)، فالنص المترجَم
 *     موجود في الذاكرة أصلًا. لو أرسل المترجَم وحده لاحتاج كل
 *     تبديل إعادة جلب كل شاشة مفتوحة — أي وميضًا وشاشات تحميل عند
 *     ضغطة يتوقّع منها المستخدم أن تكون لحظية.
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
