import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * التصنيف المرجعي — الفئات والبراندات والمصنّعون.
 *
 * ⚠️  **هذه شرطٌ لإضافة أي منتج**: الفئة إلزامية على المنتج، فمتجر
 *     بلا شاشة فئات لا يستطيع إضافة صنفه الأول من لوحته.
 *
 * ⚠️  وكلها **بلا ترقيم**: عشرات الصفوف لا آلاف، والشجرة تُقرأ
 *     كاملة أو لا تُقرأ.
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
  /** محسوب على الخادم — «sup/med/dis» */
  path: string;
  /** «أدوية ← مسكّنات» للعرض في قائمة مسطّحة */
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
 * ⚠️  إبطال **شجرة المرجع كلها وخيارات نموذج المنتج معًا**.
 *
 *     فئة جديدة يجب أن تظهر في قائمة اختيار الفئة داخل نموذج
 *     المنتج فورًا — وإلا أضافها الأدمن ثم لم يجدها حيث يحتاجها،
 *     فأعاد إضافتها.
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
 * ⚠️  الخادم يردّ ٤٠٩ برسالة **تعدّ** ما يمنع الحذف: «لهذه الفئة
 *     ١٢ منتجًا و٣ فئات فرعية». تُعرض كما هي لا تُستبدل برسالة عامة.
 */
export function useDeleteReference(kind: ReferenceKind) {
  return useReferenceMutation((id: string) =>
    http.delete<void>(`/catalog/admin/${kind}/${id}/`),
  );
}
