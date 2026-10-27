/** The `GET /api/v1/branding/theme/` contract — it matches `branding.services.theme_payload`. */

export type ThemeMode = 'LIGHT' | 'DARK';
export type DefaultMode = ThemeMode | 'SYSTEM';

export interface BrandTheme {
  code: string;
  name: Record<string, string>;
  tagline: Record<string, string>;
  assets: {
    logo_light: string;
    logo_dark: string;
    icon: string;
    favicon: string;
    og_image: string;
    /** The home banner, one per mode — empty when not uploaded. */
    hero_light: string;
    hero_dark: string;
  };
  /**
   * The home banner's text. Every field may be empty — the page then falls back to
   * the store name, the tagline and the catalogue button.
   *
   * ⚠️  Optional: a payload cached before this field existed (the server caches the
   * identity for 12 hours) simply does not have it.
   */
  hero?: {
    title: Record<string, string>;
    subtitle: Record<string, string>;
    cta_label: Record<string, string>;
    /** A path inside the store (`/offers`) or an `https://` URL; empty = the catalogue. */
    cta_url: string;
  };
  default_mode: DefaultMode;
  /** Tokens constant across both modes: the fonts and the shape. */
  tokens: Record<string, string>;
  /** A map of colour tokens per mode — ready for injection with no processing. */
  palettes: Record<ThemeMode, Record<string, string>>;
  contact: {
    email: string;
    phone: string;
    whatsapp: string;
    address: Record<string, string>;
  };
  social: Record<string, string>;
}
