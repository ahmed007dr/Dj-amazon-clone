/**
 * Picking the field matching the language from bilingual content.
 *
 * ⚠️  This is what makes switching language **instant, with no network**.
 *
 *     The server sent `name_ar` and `name_en` together (ADR-34), so the data is
 *     already in memory. Were it to send the translated one alone, every
 *     language switch would need every open screen refetched — a flash and
 *     loading screens.
 *
 *     Falling back to Arabic is deliberate: a product published in Arabic and
 *     never translated should appear under its name rather than blank.
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * Any object carrying `<field>_ar` and `<field>_en`.
 *
 * ⚠️  `object`, not `Record<string, unknown>`.
 *
 *     The latter rejects every interface with declared fields
 *     (`ProductListItem`) because it has no index signature — forcing every
 *     caller into an `as` that defeats the whole check.
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

/** A variant for an `{ ar, en }` map — as the visual identity API returns it. */
export function useLocalizedMap(): (source: Record<string, string> | undefined) => string {
  const { i18n } = useTranslation();
  const locale = i18n.language.slice(0, 2);

  return useCallback(
    (source) => source?.[locale] || source?.ar || '',
    [locale],
  );
}
