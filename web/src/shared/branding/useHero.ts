/**
 * The home page's hero — the picture for the current mode and the editable texts.
 *
 * ⚠️  Everything may be empty, and the page is built to look right when it is.
 *
 *     A profile that has never been configured must render exactly as the page did
 *     before the hero was editable: the store name as the headline, the tagline under
 *     it, a button to the catalogue, and a gradient where the picture would be. So this
 *     hook returns the raw values (empty strings included) and the caller supplies the
 *     fallbacks — only the page knows what the right ones are.
 *
 * ⚠️  The image follows the **applied** mode (`SYSTEM` already resolved), and falls back
 *     to the other mode's image before falling back to nothing. A banner in the wrong
 *     theme is a better page than the gradient, and the admin only has to upload twice
 *     when the two photographs genuinely differ.
 */

import { mediaUrl } from '@/shared/http';
import { useLocalizedMap } from '@/shared/i18n/useLocalized';
import { useTheme } from '@/shared/theme';

export interface HeroCta {
  href: string;
  /** Leaves the site: a plain anchor, not a router link. */
  external: boolean;
}

export interface Hero {
  /** A full URL, or `''` when no image is uploaded for either mode. */
  image: string;
  title: string;
  subtitle: string;
  ctaLabel: string;
  cta: HeroCta;
}

/** Where the button goes when the admin has not chosen anywhere. */
const DEFAULT_CTA: HeroCta = { href: '/products', external: false };

/**
 * ⚠️  Re-checked here although the server validates it too.
 *
 *     The value ends up in an `href` on the busiest page of the site. A stale cache, a
 *     row edited straight in the database or a future API change must not be able to turn
 *     it into `javascript:` — anything that is not a path inside the store or an `https`
 *     address silently becomes the catalogue.
 */
export function resolveCta(raw: string): HeroCta {
  const value = raw.trim();

  if (value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')) {
    return { href: value, external: false };
  }

  if (value.toLowerCase().startsWith('https:')) {
    try {
      const parsed = new URL(value);
      if (parsed.protocol === 'https:') return { href: parsed.href, external: true };
    } catch {
      /* not a URL — fall through to the default */
    }
  }

  return DEFAULT_CTA;
}

export function useHero(): Hero {
  const { theme, mode } = useTheme();
  const localized = useLocalizedMap();

  const assets = theme?.assets;
  const preferred = mode === 'DARK' ? assets?.hero_dark : assets?.hero_light;
  const other = mode === 'DARK' ? assets?.hero_light : assets?.hero_dark;

  return {
    image: mediaUrl(preferred || other),
    title: localized(theme?.hero?.title),
    subtitle: localized(theme?.hero?.subtitle),
    ctaLabel: localized(theme?.hero?.cta_label),
    cta: resolveCta(theme?.hero?.cta_url ?? ''),
  };
}
