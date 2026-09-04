import type { JSX } from 'react';

import { useBrand } from '@/shared/branding/useBrand';

import './SocialLinks.css';

/**
 * The brand mark for each platform — plain shapes (`rect`/`circle`/`path`),
 * not traced logo artwork, and every stroke uses `currentColor`.
 *
 * ⚠️  `currentColor`, not a fixed brand colour.
 *
 *     `.social-links__item` sets `color` and transitions it on hover — a
 *     hardcoded fill would freeze every icon at one colour and break that
 *     hover state along with dark mode.
 */
const ICONS: Record<string, () => JSX.Element> = {
  facebook: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <path
        fill="currentColor"
        d="M14 13.5h2.5l.4-3H14V8.5c0-.9.2-1.5 1.5-1.5H17V4.2C16.7 4.1 15.7 4 14.5 4 12 4 10.5 5.5 10.5 8.2V10.5H8v3h2.5V20h3.5v-6.5z"
      />
    </svg>
  ),
  instagram: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="17.2" cy="6.8" r="1.1" fill="currentColor" />
    </svg>
  ),
  x: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <path d="M4 4l16 16M20 4L4 20" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none" />
    </svg>
  ),
  linkedin: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <rect x="4" y="9" width="2.6" height="9" fill="currentColor" />
      <circle cx="5.3" cy="5.5" r="1.6" fill="currentColor" />
      <path
        fill="currentColor"
        d="M10 9h2.5v1.5c.7-1.1 1.9-1.8 3.3-1.8 2.6 0 4.2 1.7 4.2 4.9V18h-2.6v-3.8c0-1.7-.6-2.7-2-2.7-1.5 0-2.4 1-2.4 2.7V18H10V9z"
      />
    </svg>
  ),
  youtube: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <rect x="3" y="6" width="18" height="12" rx="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path fill="currentColor" d="M10.5 9.5l5 2.5-5 2.5v-5z" />
    </svg>
  ),
  tiktok: () => (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <path
        fill="currentColor"
        d="M14 4v10.2a2.7 2.7 0 1 1-2.2-2.66V9.1a5.2 5.2 0 1 0 4.7 5.17V9.9c1 .7 2.2 1.1 3.5 1.1V8.5c-1.7 0-3.1-1-3.6-2.5-.2-.6-.3-1.3-.3-2H14z"
      />
    </svg>
  ),
};

/**
 * ⚠️  Empty links are not displayed.
 *
 *     An icon leading to an empty page is worse than its absence — and the admin
 *     leaves the field empty when they do not have the account, not in order to
 *     create it later.
 */
export function SocialLinks() {
  const { social } = useBrand();

  const entries = Object.entries(social).filter(([, url]) => Boolean(url));
  if (entries.length === 0) return null;

  return (
    <ul className="social-links">
      {entries.map(([key, url]) => {
        const Icon = ICONS[key];
        return (
          <li key={key}>
            <a
              href={url}
              target="_blank"
              rel="noreferrer noopener"
              aria-label={key}
              className="social-links__item"
            >
              {Icon ? <Icon /> : <span aria-hidden>•</span>}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
