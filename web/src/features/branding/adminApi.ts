import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

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

/** الأصول الخمسة — كلها صور يرفعها الأدمن. */
export type AssetField = 'logo_light' | 'logo_dark' | 'icon' | 'favicon' | 'og_image';

export const ASSET_FIELDS: AssetField[] = [
  'logo_light',
  'logo_dark',
  'icon',
  'favicon',
  'og_image',
];

export interface AdminBrandProfile {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  tagline_ar: string;
  tagline_en: string;
  /** مسارات نسبية — تُحوَّل بـ `mediaUrl` قبل العرض */
  logo_light: string | null;
  logo_dark: string | null;
  icon: string | null;
  favicon: string | null;
  og_image: string | null;
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

// ═══════════════════════════════════════════════════════════
//  الخطّافات
// ═══════════════════════════════════════════════════════════

export const BRANDING_KEY = ['admin', 'branding'] as const;

/**
 * ⚠️  إبطال **شجرة الهوية والثيم العام معًا** بعد أي كتابة.
 *
 *     الأولى تحدّث شاشة التحرير، والثاني هو ما يجعل الأدمن يرى
 *     اللوجو الجديد في ترويسة لوحته فورًا بدل إعادة تحميل الصفحة.
 */
function useBrandingMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BRANDING_KEY });
      void queryClient.invalidateQueries({ queryKey: ['branding', 'theme'] });
    },
  });
}

export function useBrandProfiles() {
  return useQuery({ queryKey: BRANDING_KEY, queryFn: listProfiles });
}

export function useUpdateProfile() {
  return useBrandingMutation(
    ({ id, body }: { id: string; body: Partial<AdminBrandProfile> }) => updateProfile(id, body),
  );
}

/**
 * رفع أصل واحد.
 *
 * ⚠️  `FormData` لا JSON — الحمولة ملف.
 *
 * ⚠️  و**حقل واحد لكل نداء**: إرسال الخمسة معًا يعني أن رفض ملف
 *     منها يُفشل الأربعة الأخرى، والأدمن يعيد اختيارها كلها.
 */
export function useUploadAsset() {
  return useBrandingMutation(({ id, field, file }: { id: string; field: AssetField; file: File }) => {
    const body = new FormData();
    body.append(field, file);
    return http.patch<AdminBrandProfile>(`/branding/admin/profiles/${id}/`, body);
  });
}

/**
 * المسح — **JSON بقيمة `null` لا نموذجًا بقيمة فارغة**.
 *
 * ⚠️  الحقل الفارغ في حمولة `multipart` يتجاهله DRF بصمت: يردّ ٢٠٠
 *     ويُبقي الصورة مكانها. فيضغط الأدمن «حذف» ويرى نجاحًا واللوجو
 *     لم يتغيّر — وهو أسوأ أنواع الفشل لأنه يبدو نجاحًا.
 */
export function useClearAsset() {
  return useBrandingMutation(({ id, field }: { id: string; field: AssetField }) =>
    http.patch<AdminBrandProfile>(`/branding/admin/profiles/${id}/`, { [field]: null }),
  );
}

export function useActivateProfile() {
  return useBrandingMutation((id: string) => activateProfile(id));
}

export function useUpdatePalette() {
  return useBrandingMutation(
    ({
      profileId,
      paletteId,
      body,
    }: {
      profileId: string;
      paletteId: string;
      body: Partial<AdminPalette>;
    }) => updatePalette(profileId, paletteId, body),
  );
}
