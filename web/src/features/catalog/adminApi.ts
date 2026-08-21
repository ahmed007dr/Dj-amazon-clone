import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

/**
 * ⚠️  A soft-deleted product **stays visible to the admin** through the `include_deleted` flag.
 *
 *     A soft delete with no way to see what was deleted is a permanent delete
 *     from the user's point of view — and the first question after an
 *     accidental delete is "where did it go?".
 *
 * ⚠️  **It does not inherit `ProductDetail`** — and that is a correction, not a detail.
 *
 *     `AdminProductSerializer` is a `ModelSerializer` stripped of relations:
 *     `category`, `brand` and `manufacturer` come back as **string ids**, not
 *     objects, and there is no `images`, no `rating` and no `primary_image`.
 *     The inheritance promised fields the server does not send, so the static
 *     check passed while the screen displayed nothing:
 *     `localized(uuid, 'name')` returns an empty string with no error — which
 *     is exactly what was happening in the category column.
 */
export interface AdminProduct {
  id: string;
  slug: string;
  sku: string;
  barcode: string;
  name_ar: string;
  name_en: string;
  short_description_ar: string;
  short_description_en: string;
  description_ar: string;
  description_en: string;
  kind: string;
  base_price: string;

  /** Ids, not objects — their names are resolved from `useProductFormOptions` */
  category: string | null;
  brand: string | null;
  manufacturer: string | null;
  tax_class: string | null;
  access_policy: string | null;

  regulatory_class: string;
  requires_prescription: boolean;
  registration_number: string;
  active_ingredient_ar: string;
  active_ingredient_en: string;
  strength: string;
  dosage_form: string;
  pack_size: string;
  storage_condition: string;
  weight_grams: number | null;

  is_active: boolean;
  is_featured: boolean;
  published_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminProductQuery {
  search?: string;
  category?: string;
  is_active?: string;
  include_deleted?: string;
  page?: number;
}

export const listAdminProducts = (params: AdminProductQuery) =>
  http.get<PagedResponse<AdminProduct>>('/catalog/admin/products/', { params: { ...params } });

export const updateAdminProduct = (id: string, body: Partial<AdminProduct>) =>
  http.patch<AdminProduct>(`/catalog/admin/products/${id}/`, body);

// ═══════════════════════════════════════════════════════════
//  Form options
// ═══════════════════════════════════════════════════════════

export interface Choice {
  value: string;
  label: string;
}

export interface CategoryOption {
  id: string;
  name_ar: string;
  name_en: string;
  /** The full path — "Medicines ← Painkillers ← Tablets" */
  path_label: string;
}

export interface NamedOption {
  id: string;
  name_ar: string;
  name_en: string;
}

/**
 * An access policy — the answer to "who sees this product?".
 *
 * ⚠️  Both conditions are shown alongside the name rather than after it:
 *     "verified professionals" alone does not say that a registered but
 *     unverified doctor is blocked.
 */
export interface AccessPolicyOption {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  level: string;
  is_default: boolean;
  requires_verification: boolean;
  allowed_account_types: string[];
  description_ar: string;
  description_en: string;
}

export interface TaxClassOption {
  id: string;
  name_ar: string;
  name_en: string;
  rate: string;
  is_default: boolean;
}

export interface ProductFormOptions {
  kinds: Choice[];
  regulatory_classes: Choice[];
  dosage_forms: Choice[];
  storage_conditions: Choice[];
  categories: CategoryOption[];
  brands: NamedOption[];
  manufacturers: NamedOption[];
  access_policies: AccessPolicyOption[];
  tax_classes: TaxClassOption[];
}

/**
 * ⚠️  The lists come from the server rather than being duplicated here.
 *
 *     Hard-coding the dosage forms in frontend code means a value added on the
 *     server never reaches the admin, and one removed leaves an option that
 *     fails on save.
 *
 * ⚠️  And a long stale time: this is reference data that changes by the month,
 *     not the minute, and refetching it every time the form opens slows the
 *     screen for nothing.
 */
export function useProductFormOptions(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'product-options'],
    queryFn: () => http.get<ProductFormOptions>('/catalog/admin/products/options/'),
    staleTime: 30 * 60 * 1000,
    enabled,
  });
}

// ═══════════════════════════════════════════════════════════
//  Writing
// ═══════════════════════════════════════════════════════════

/**
 * ⚠️  Invalidate the product list **and the form options together** after any write.
 *
 *     The list alone suffices for a delete or an edit, but a new product may be
 *     the first assigned to a category, leaving the screen's counter stale.
 */
function useProductMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'products'] }),
  });
}

export type ProductDraft = Record<string, unknown>;

export function useCreateProduct() {
  return useProductMutation((body: ProductDraft) =>
    http.post<AdminProduct>('/catalog/admin/products/', body),
  );
}

export function useUpdateProduct() {
  return useProductMutation(({ id, body }: { id: string; body: ProductDraft }) =>
    http.patch<AdminProduct>(`/catalog/admin/products/${id}/`, body),
  );
}

/**
 * ⚠️  A soft delete on the server — the row remains and historical orders point at it.
 *     Which is why it is paired with `useRestoreProduct` rather than a hard delete.
 */
export function useDeleteProduct() {
  return useProductMutation((id: string) =>
    http.delete<void>(`/catalog/admin/products/${id}/`),
  );
}

export function useRestoreProduct() {
  return useProductMutation((id: string) =>
    http.post<AdminProduct>(`/catalog/admin/products/${id}/restore/`),
  );
}
