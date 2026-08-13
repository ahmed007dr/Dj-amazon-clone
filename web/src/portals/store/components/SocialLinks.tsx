import { useBrand } from '@/shared/branding/useBrand';

import './SocialLinks.css';

/** المفتاح في حمولة الهوية → الرمز المعروض. */
const ICONS: Record<string, string> = {
  facebook: 'f',
  instagram: '◎',
  x: '𝕏',
  linkedin: 'in',
  youtube: '▶',
  tiktok: '♪',
};

/**
 * ⚠️  الروابط الفارغة لا تُعرض.
 *
 *     أيقونة تؤدي إلى صفحة فارغة أسوأ من غيابها — والأدمن يترك
 *     الحقل فارغًا حين لا يملك الحساب، لا لينشئه لاحقًا.
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
