/**
 * حقن رموز الثيم في عنصر الجذر.
 *
 * ⚠️  الرموز تأتي **جاهزة** من الخادم (`--color-primary: #…`).
 *
 *     بناء أسماء الرموز في الواجهة يعني تكرارها في مستودعين، فتصير
 *     إضافة لون واحد تعديلين — وأحدهما يُنسى.
 */

import type { BrandTheme, ThemeMode } from './types';

export function applyTheme(theme: BrandTheme, mode: ThemeMode): void {
  const root = document.documentElement;

  for (const [token, value] of Object.entries(theme.tokens)) {
    root.style.setProperty(token, value);
  }

  for (const [token, value] of Object.entries(theme.palettes[mode] ?? {})) {
    root.style.setProperty(token, value);
  }

  root.dataset.theme = mode === 'DARK' ? 'dark' : 'light';

  // ⚠️  يخبر المتصفح بلون واجهاته الأصلية (شريط التمرير · حقول
  //     الإدخال). بدونه تبقى بيضاء داخل صفحة داكنة.
  root.style.colorScheme = mode === 'DARK' ? 'dark' : 'light';
}

/** يحدّث أيقونة التبويب حين يرفع الأدمن أيقونة جديدة. */
export function applyFavicon(href: string): void {
  if (!href) return;

  const link =
    document.querySelector<HTMLLinkElement>("link[rel='icon']") ??
    document.head.appendChild(Object.assign(document.createElement('link'), { rel: 'icon' }));

  link.href = href;
}
