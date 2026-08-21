/**
 * The **single** source for the server's addresses. (ADR-19)
 *
 * ⚠️  This file is the only exception permitted to read `import.meta.env` — an
 *     ESLint rule refuses it everywhere else.
 *
 *     The reason is not elegance: an address scattered across twenty files means
 *     switching environments is a search-and-replace operation, and that a
 *     single forgotten file makes production hit the development server — a
 *     silent error that shows up in no test.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    // ⚠️  Fail loudly at boot rather than falling back to a default value.
    //
    //     A silent default (`?? 'http://localhost:8000'`) produces a deployment that
    //     looks successful and then fails on every call at the first user.
    throw new Error(
      `متغيّر البيئة ${name} غير مضبوط. انسخ .env.example إلى .env واضبطه.`,
    );
  }
  return value.replace(/\/+$/, '');
}

export const BASE_URL = required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL);

export const MEDIA_BASE_URL = required(
  'VITE_MEDIA_BASE_URL',
  import.meta.env.VITE_MEDIA_BASE_URL,
);

export const DEFAULT_LOCALE = (import.meta.env.VITE_DEFAULT_LOCALE ?? 'ar') as 'ar' | 'en';

/**
 * A media path → a full URL.
 *
 * ⚠️  The server sometimes returns a relative path (`/media/…`) and sometimes a
 *     full URL (when the media sits on a CDN). Handling both cases here avoids
 *     repeating the check in every component that displays an image.
 */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${MEDIA_BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
}
