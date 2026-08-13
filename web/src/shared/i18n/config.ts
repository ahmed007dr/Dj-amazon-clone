/**
 * إعداد الترجمة.
 *
 * ⚠️  التمييز الحاسم: **ترجمة الواجهة ≠ ترجمة المحتوى.**
 *
 *         الواجهة  →  ملفات JSON هنا     (أزرار · عناوين · رسائل)
 *         المحتوى  →  الخادم، باللغتين   (أسماء منتجات · أوصاف)
 *
 *     الخادم يرسل `name_ar` و`name_en` معًا دائمًا (ADR-34). ولهذا
 *     **تبديل اللغة لا يحتاج إعادة جلب أي شيء** — البيانات في
 *     الذاكرة أصلًا تحمل اللغتين، والواجهة تختار الحقل.
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

  // ⚠️  تفضيل المتصفح قبل الافتراضي: زائر بمتصفح إنجليزي يرى
  //     إنجليزية من أول ثانية بلا نقرة.
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
  // رسائل أخطاء الخادم تُترجَم بهذه الترويسة
  setRequestLocale(locale);
});

export default i18n;

export function isRtl(locale: string): boolean {
  return (RTL_LOCALES as readonly string[]).includes(locale.slice(0, 2));
}
