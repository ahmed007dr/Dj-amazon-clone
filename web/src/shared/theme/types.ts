/** The `GET /api/v1/branding/theme/` contract — it matches `branding.services.theme_payload`. */

export type ThemeMode = 'LIGHT' | 'DARK';
export type DefaultMode = ThemeMode | 'SYSTEM';

/** Matches `branding.models.ChannelKind`. */
export type ChannelKind =
  | 'WHATSAPP'
  | 'TELEGRAM'
  | 'PHONE'
  | 'EMAIL'
  | 'FACEBOOK'
  | 'INSTAGRAM'
  | 'TIKTOK'
  | 'YOUTUBE'
  | 'X'
  | 'SNAPCHAT'
  | 'LINKEDIN'
  | 'WEBSITE'
  | 'MAP'
  | 'OTHER';

/**
 * One public "Contact us" channel — `branding.services.public_channels`.
 *
 * ⚠️  Everything here is **computed on the server**: `href` is built there from the
 * validated value (never the admin's raw text), and `value` is the display text. The
 * page paints them as they come and builds no link of its own.
 */
export interface ContactChannel {
  kind: ChannelKind;
  /** The admin's label, or the kind's default — both languages. */
  label: Record<string, string>;
  /** What the visitor reads: `+20 10 1234 5678`, `@store`, `example.com/page`. */
  value: string;
  /** `https:`, `tel:` or `mailto:` — WhatsApp carries the Arabic prefilled message. */
  href: string;
  /** The same link with the English prefilled message (equal to `href` for every other kind). */
  href_en?: string;
  order: number;
  /** An active WhatsApp channel that earns the floating chat button. */
  floating: boolean;
}

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
  /**
   * Additional ways to reach the store, active ones in display order. They sit
   * **beside** `contact` and `social`, which keep rendering as before.
   *
   * ⚠️  Optional: a payload cached before this field existed (12 hours) lacks it.
   */
  contact_channels?: ContactChannel[];
}
