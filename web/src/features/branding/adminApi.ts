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
  /** ⚠️  Computed on every display — storing it means a figure going stale at the first edit. */
  contrast: ContrastEntry[];
}

/** The five assets — all images uploaded by the admin. */
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
  /** Relative paths — converted with `mediaUrl` before display */
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
 * Preview a palette **before saving it**.
 *
 * ⚠️  It writes nothing to the server.
 *
 *     "Try it and undo" on the identity means every visitor during the attempt
 *     saw broken colours. The preview computes the tokens and the contrast and
 *     returns them without touching what is active.
 */
export const previewPalette = (body: Partial<AdminPalette>) =>
  http.post<{
    tokens: Record<string, string>;
    contrast: ContrastEntry[];
    passes_aa: boolean;
  }>('/branding/admin/preview/', body);

/**
 * Create a new identity.
 *
 * ⚠️  **The screen could not create its own first profile until this existed.**
 *
 *     `AdminBrandingPage` stops at an empty state when the list is empty, and
 *     the list starts empty on any installation that never ran the development
 *     seed. The server accepted POST all along — nothing here called it — so the
 *     panel was unusable and could not be repaired from inside itself.
 *
 * ⚠️  Only the three identifying fields are sent. The server creates both
 *     palettes itself (`ProfileListCreateAPI.perform_create`), because a profile
 *     without colours blanks the site the moment it is activated.
 *
 *     And it is created inactive: activating is a separate, deliberate step.
 */
export const createProfile = (body: { code: string; name_ar: string; name_en: string }) =>
  http.post<AdminBrandProfile>('/branding/admin/profiles/', body);

export const activateProfile = (id: string) =>
  http.post<AdminBrandProfile>(`/branding/admin/profiles/${id}/activate/`);

// ═══════════════════════════════════════════════════════════
//  Hooks
// ═══════════════════════════════════════════════════════════

export const BRANDING_KEY = ['admin', 'branding'] as const;

/**
 * ⚠️  Invalidate **the identity tree and the public theme together** after any write.
 *
 *     The first refreshes the editing screen, and the second is what makes the
 *     admin see the new logo in their panel's header immediately rather than
 *     reloading the page.
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

export function useCreateProfile() {
  return useBrandingMutation(createProfile);
}

export function useUpdateProfile() {
  return useBrandingMutation(
    ({ id, body }: { id: string; body: Partial<AdminBrandProfile> }) => updateProfile(id, body),
  );
}

/**
 * Upload a single asset.
 *
 * ⚠️  `FormData`, not JSON — the payload is a file.
 *
 * ⚠️  And **one field per call**: sending all five together means a rejection of
 *     one file fails the other four, and the admin re-selects them all.
 */
export function useUploadAsset() {
  return useBrandingMutation(({ id, field, file }: { id: string; field: AssetField; file: File }) => {
    const body = new FormData();
    body.append(field, file);
    return http.patch<AdminBrandProfile>(`/branding/admin/profiles/${id}/`, body);
  });
}

/**
 * Clearing — **JSON with a `null` value, not a form with an empty value**.
 *
 * ⚠️  An empty field in a `multipart` payload is silently ignored by DRF: it
 *     answers 200 and leaves the image in place. So the admin presses "delete",
 *     sees success, and the logo has not changed — the worst kind of failure,
 *     because it looks like success.
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
