import { useBrand } from '@/shared/branding/useBrand';

import './SocialLinks.css';

/** The key in the identity payload → the icon displayed. */
const ICONS: Record<string, string> = {
  facebook: 'f',
  instagram: '◎',
  x: '𝕏',
  linkedin: 'in',
  youtube: '▶',
  tiktok: '♪',
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
      {entries.map(([key, url]) => (
        <li key={key}>
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            aria-label={key}
            className="social-links__item"
          >
            <span aria-hidden>{ICONS[key] ?? '•'}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}
