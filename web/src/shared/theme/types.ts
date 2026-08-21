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
