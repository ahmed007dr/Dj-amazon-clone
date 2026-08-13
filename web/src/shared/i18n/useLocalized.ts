/**
 * اختيار الحقل المطابق للغة من محتوى ثنائي اللغة.
 *
 * ⚠️  هذا هو ما يجعل تبديل اللغة **فوريًا بلا شبكة**.
 *
 *     الخادم أرسل `name_ar` و`name_en` معًا (ADR-34)، فالبيانات في
 *     الذاكرة أصلًا. لو كان يرسل المترجَم وحده لاحتاج كل تبديل
 *     لغة إعادة جلب كل شاشة مفتوحة — ووميضًا وشاشات تحميل.
 *
 *     الارتداد إلى العربية مقصود: منتج نُشر بالعربية ولم يُترجم
 *     يجب أن يظهر باسمه لا فارغًا.
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * أي كائن يحمل `<field>_ar` و`<field>_en`.
 *
 * ⚠️  `object` لا `Record<string, unknown>`.
 *
 *     الثاني يرفض كل واجهة مصرَّحة الحقول (`ProductListItem`) لأنها
 *     بلا توقيع فهرسة — فيضطر كل مستدعٍ إلى `as` يُبطل الفحص كله.
 */
type Bilingual = object;

export function useLocalized(): (source: Bilingual, field: string) => string {
  const { i18n } = useTranslation();
  const locale = i18n.language.slice(0, 2);

  return useCallback(
    (source, field) => {
      const record = source as Record<string, unknown>;

      const preferred = record[`${field}_${locale}`];
      if (typeof preferred === 'string' && preferred) return preferred;

      const fallback = record[`${field}_ar`];
      return typeof fallback === 'string' ? fallback : '';
    },
    [locale],
  );
}

/** نسخة لخريطة `{ ar, en }` — كما تعيدها واجهة الهوية البصرية. */
export function useLocalizedMap(): (source: Record<string, string> | undefined) => string {
  const { i18n } = useTranslation();
  const locale = i18n.language.slice(0, 2);

  return useCallback(
    (source) => source?.[locale] || source?.ar || '',
    [locale],
  );
}
