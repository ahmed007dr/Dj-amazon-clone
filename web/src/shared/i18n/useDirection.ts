/**
 * يربط لغة `i18next` بسمتَي `lang` و`dir` على عنصر الجذر.
 *
 * ⚠️  الاتجاه **من الجذر وحده**.
 *
 *     تثبيت `dir` أو `text-align` داخل مكوّن يعني مكوّنًا لا ينقلب
 *     مع بقية الصفحة — والنتيجة تخطيط نصفه يمين ونصفه يسار. مع
 *     الخصائص المنطقية (`margin-inline-start`) لا يحتاج أي مكوّن
 *     أن يعرف الاتجاه أصلًا.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { isRtl, type Locale } from './config';

export function useDirection(): {
  locale: Locale;
  dir: 'rtl' | 'ltr';
  setLocale: (next: Locale) => void;
} {
  const { i18n } = useTranslation();
  const locale = i18n.language.slice(0, 2) as Locale;
  const dir = isRtl(locale) ? 'rtl' : 'ltr';

  useEffect(() => {
    const root = document.documentElement;
    root.lang = locale;
    root.dir = dir;
    // ⚠️  رمز الخط يتبدّل مع اللغة: خط لاتيني جيد قد لا يحمل
    //     محارف عربية، فيسقط النص إلى خط النظام بلا تحذير.
    root.style.setProperty('--font-active', `var(--font-${locale})`);
  }, [locale, dir]);

  return {
    locale,
    dir,
    setLocale: (next: Locale) => {
      void i18n.changeLanguage(next);
    },
  };
}
