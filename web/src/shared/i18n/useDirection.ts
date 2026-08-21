/**
 * Binds the `i18next` language to the `lang` and `dir` attributes on the root element.
 *
 * ⚠️  The direction comes **from the root alone**.
 *
 *     Hard-coding `dir` or `text-align` inside a component means a component
 *     that does not flip with the rest of the page — and the result is a layout
 *     half right-to-left and half left-to-right. With logical properties
 *     (`margin-inline-start`) no component needs to know the direction at all.
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
    // ⚠️  The font token switches with the language: a good Latin font may not carry
    //     Arabic glyphs, so the text falls back to the system font with no warning.
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
