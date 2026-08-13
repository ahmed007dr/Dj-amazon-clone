/** عقد `GET /api/v1/branding/theme/` — يطابق `branding.services.theme_payload`. */

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
  /** رموز ثابتة عبر الوضعين: الخطوط والشكل. */
  tokens: Record<string, string>;
  /** خريطة رموز لونية لكل وضع — جاهزة للحقن بلا معالجة. */
  palettes: Record<ThemeMode, Record<string, string>>;
  contact: {
    email: string;
    phone: string;
    whatsapp: string;
    address: Record<string, string>;
  };
  social: Record<string, string>;
}
