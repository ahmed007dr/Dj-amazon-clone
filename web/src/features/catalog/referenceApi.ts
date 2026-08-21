import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * Reference classification — categories, brands and manufacturers.
 *
 * ⚠️  **This is a precondition for adding any product**: the category is
 *     mandatory on a product, so a store with no categories screen cannot add
 *     its first item from its panel.
 *
 * ⚠️  And all of them are **unpaginated**: tens of rows, not thousands, and the
 *     tree is read in full or not at all.
 */

export interface AdminCategory {
  id: string;
  slug: string;
  parent: string | null;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  image: string | null;
  icon: string;
  /** Computed on the server — "sup/med/dis" */
  path: string;
  /** "Medicines ← Painkillers" for display in a flat list */
  path_label: string;
  depth: number;
  display_order: number;
  is_active: boolean;
  show_in_menu: boolean;
  product_count: number;
}

export interface AdminManufacturer {
  id: string;
  slug: string;
  name_ar: string;
  name_en: string;
  country: string;
  registration_number: string;
  website: string;
  logo: string | null;
  is_active: boolean;
  brand_count: number;
}

export interface AdminBrand {
  id: string;
  slug: string;
  manufacturer: string | null;
  manufacturer_name: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  logo: string | null;
  display_order: number;
  is_featured: boolean;
  is_active: boolean;
  product_count: number;
}

export type ReferenceKind = 'categories' | 'brands' | 'manufacturers';

const KEY = (kind: ReferenceKind) => ['admin', 'reference', kind] as const;

export function useCategories(enabled = true) {
  return useQuery({
    queryKey: KEY('categories'),
    queryFn: () => http.get<AdminCategory[]>('/catalog/admin/categories/'),
    enabled,
  });
}

export function useManufacturers(enabled = true) {
  return useQuery({
    queryKey: KEY('manufacturers'),
    queryFn: () => http.get<AdminManufacturer[]>('/catalog/admin/manufacturers/'),
    enabled,
  });
}

export function useBrands(enabled = true) {
  return useQuery({
    queryKey: KEY('brands'),
    queryFn: () => http.get<AdminBrand[]>('/catalog/admin/brands/'),
    enabled,
  });
}

/**
 * ⚠️  Invalidate **the whole reference tree and the product form options together**.
 *
 *     A new category must appear in the category select inside the product form
 *     immediately — otherwise the admin adds it, cannot find it where they need
 *     it, and adds it again.
 */
function useReferenceMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'reference'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'product-options'] });
    },
  });
}

export type ReferenceDraft = Record<string, unknown>;

export function useCreateReference(kind: ReferenceKind) {
  return useReferenceMutation((body: ReferenceDraft) =>
    http.post(`/catalog/admin/${kind}/`, body),
  );
}

export function useUpdateReference(kind: ReferenceKind) {
  return useReferenceMutation(({ id, body }: { id: string; body: ReferenceDraft }) =>
    http.patch(`/catalog/admin/${kind}/${id}/`, body),
  );
}

/**
 * ⚠️  The server answers 409 with a message that **counts** what blocks the
 *     deletion: "this category has 12 products and 3 subcategories". It is
 *     displayed as it is, never replaced with a generic message.
 */
export function useDeleteReference(kind: ReferenceKind) {
  return useReferenceMutation((id: string) =>
    http.delete<void>(`/catalog/admin/${kind}/${id}/`),
  );
}
