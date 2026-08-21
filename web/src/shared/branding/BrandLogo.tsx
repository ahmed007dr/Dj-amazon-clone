import { mediaUrl } from '@/shared/http';
import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { useTheme } from '@/shared/theme';

import './BrandLogo.css';

/**
 * The base logo — it reads the identity from the server.
 *
 * ⚠️  A logo per mode rather than a single logo.
 *
 *     A logo with a transparent background and dark text disappears entirely in
 *     dark mode — and nobody notices, because the screen looks fine, just with
 *     no mark on it.
 *
 * ⚠️  This component is **not called directly in pages**. Every portal wraps it
 *     in its own version (`portals/<portal>/components/Logo.tsx`) because its
 *     size, its destination and its shape differ: the store returns to the home
 *     page, and the point of sale does not leave the screen at all.
 */
export function BrandLogo({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const { theme, mode } = useTheme();
  const localized = useLocalizedMap();

  const name = localized(theme?.name) || '';
  const source = mode === 'DARK' ? theme?.assets.logo_dark : theme?.assets.logo_light;
  const fallback = theme?.assets.logo_light || theme?.assets.logo_dark;
  const href = mediaUrl(source || fallback);

  if (href) {
    return <img className={`brand-logo brand-logo--${size}`} src={href} alt={name} />;
  }

  // ⚠️  A text fallback rather than an empty square.
  //
  //     The identity before the admin uploads a logo — the default state on the
  //     first day of operation. An empty square looks like a fault.
  return (
    <span className={`brand-logo brand-logo--text brand-logo--${size}`} aria-label={name}>
      {name}
    </span>
  );
}
