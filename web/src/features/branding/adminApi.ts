import { http } from '@/shared/http';

export interface ContrastEntry {
  key: string;
  label: string;
  foreground: string;
  background: string;
  ratio: number;
  passes_aa: boolean;
  passes_aa_large: boolean;
}

export interface AdminPalette {
  id: string;
  mode: 'LIGHT' | 'DARK';
  primary: string;
  on_primary: string;
  secondary: string;
  accent: string;
  success: string;
  warning: string;
  danger: string;
  info: string;
  bg: string;
  surface: string;
  border: string;
  text: string;
  text_muted: string;
  /** ⚠️  يُحسب عند كل عرض — تخزينه يعني رقمًا يتقادم عند أول تعديل. */
  contrast: ContrastEntry[];
}

export interface AdminBrandProfile {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  tagline_ar: string;
  tagline_en: string;
  font_ar: string;
  font_en: string;
  font_size_base: string;
  radius: string;
  shadow_level: number;
  default_mode: 'LIGHT' | 'DARK' | 'SYSTEM';
  contact_email: string;
  contact_phone: string;
  whatsapp: string;
  address_ar: string;
  address_en: string;
  facebook: string;
  instagram: string;
  x_twitter: string;
  linkedin: string;
  youtube: string;
  tiktok: string;
  is_active: boolean;
  palettes: AdminPalette[];
}

export const listProfiles = () => http.get<AdminBrandProfile[]>('/branding/admin/profiles/');

export const updateProfile = (id: string, body: Partial<AdminBrandProfile>) =>
  http.patch<AdminBrandProfile>(`/branding/admin/profiles/${id}/`, body);

export const updatePalette = (
  profileId: string,
  paletteId: string,
  body: Partial<AdminPalette>,
) => http.patch<AdminPalette>(`/branding/admin/profiles/${profileId}/palettes/${paletteId}/`, body);

/**
 * معاينة لوحة **قبل حفظها**.
 *
 * ⚠️  لا تكتب شيئًا في الخادم.
 *
 *     «جرّب ثم تراجع» على الهوية يعني أن كل زائر خلال المحاولة رأى
 *     ألوانًا مكسورة. المعاينة تحسب الرموز والتباين وتعيدهما بلا
 *     مساس بالمفعّل.
 */
export const previewPalette = (body: Partial<AdminPalette>) =>
  http.post<{
    tokens: Record<string, string>;
    contrast: ContrastEntry[];
    passes_aa: boolean;
  }>('/branding/admin/preview/', body);

export const activateProfile = (id: string) =>
  http.post<AdminBrandProfile>(`/branding/admin/profiles/${id}/activate/`);
