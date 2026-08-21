/**
 * Translation setup.
 *
 * ⚠️  The decisive distinction: **interface translation ≠ content translation.**
 *
 *         Interface  →  the JSON files here    (buttons · titles · messages)
 *         Content    →  the server, in both    (product names · descriptions)
 *
 *     The server always sends `name_ar` and `name_en` together (ADR-34). Which
 *     is why **switching language requires refetching nothing** — the data
 *     already in memory carries both languages, and the frontend picks the field.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { DEFAULT_LOCALE, setRequestLocale } from '@/shared/http';

import ar from './locales/ar.json';
import en from './locales/en.json';

export const LOCALES = ['ar', 'en'] as const;
export type Locale = (typeof LOCALES)[number];

export const RTL_LOCALES: readonly Locale[] = ['ar'];

const STORAGE_KEY = 'locale';

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && (LOCALES as readonly string[]).includes(stored)) return stored as Locale;

  // ⚠️  The browser's preference before the default: a visitor with an English
  //     browser sees English from the first second with no click.
  const browser = navigator.language.slice(0, 2);
  if ((LOCALES as readonly string[]).includes(browser)) return browser as Locale;

  return DEFAULT_LOCALE;
}

void i18n.use(initReactI18next).init({
  resources: {
    ar: { translation: ar },
    en: { translation: en },
  },
  lng: initialLocale(),
  fallbackLng: 'ar',
  interpolation: { escapeValue: false },
  returnNull: false,
});

setRequestLocale(i18n.language);

i18n.on('languageChanged', (locale) => {
  localStorage.setItem(STORAGE_KEY, locale);
  // The server's error messages are translated using this header
  setRequestLocale(locale);
});

export default i18n;

export function isRtl(locale: string): boolean {
  return (RTL_LOCALES as readonly string[]).includes(locale.slice(0, 2));
}
