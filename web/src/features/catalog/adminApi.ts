import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

/**
 * ⚠️  المنتج المحذوف ناعمًا **يبقى مرئيًا للأدمن** بعلم `include_deleted`.
 *
 *     الحذف الناعم بلا طريقة لرؤية المحذوف يجعله حذفًا نهائيًا من
 *     منظور المستخدم — وأول سؤال بعد حذف بالخطأ هو «أين ذهب؟».
 *
 * ⚠️  **لا يرث `ProductDetail`** — وهذا تصحيح لا تفصيل.
 *
 *     `AdminProductSerializer` هو `ModelSerializer` عاري العلاقات:
 *     `category` و`brand` و`manufacturer` تعود **معرّفات نصية** لا
 *     كائنات، ولا وجود لـ `images` ولا `rating` ولا `primary_image`.
 *     الوراثة كانت تَعِد بحقول لا يرسلها الخادم، فيمرّ الفحص
 *     الثابت بينما تعرض الشاشة فراغًا: `localized(uuid, 'name')`
 *     تعيد سلسلة فارغة بلا خطأ — وهو بالضبط ما كان يحدث في عمود
 *     الفئة.
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

  /** معرّفات لا كائنات — تُحلّ أسماؤها من `useProductFormOptions` */
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
//  خيارات النموذج
// ═══════════════════════════════════════════════════════════

export interface Choice {
  value: string;
  label: string;
}

export interface CategoryOption {
  id: string;
  name_ar: string;
  name_en: string;
  /** المسار الكامل — «أدوية ← مسكّنات ← أقراص» */
  path_label: string;
}

export interface NamedOption {
  id: string;
  name_ar: string;
  name_en: string;
}

/**
 * سياسة وصول — جواب السؤال «مَن يرى هذا المنتج؟».
 *
 * ⚠️  الشرطان يُعرضان مع الاسم لا بعده: «مهنيون موثّقون» وحدها لا
 *     تقول إن الطبيب المسجَّل غير الموثّق ممنوع.
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
 * ⚠️  القوائم من الخادم لا مكرّرة هنا.
 *
 *     تثبيت الأشكال الدوائية في كود الواجهة يجعل إضافة قيمة في
 *     الخادم لا تظهر للأدمن، وحذفها يترك خيارًا يفشل عند الحفظ.
 *
 * ⚠️  ومهلة طويلة: هذه بيانات مرجعية تتغيّر بالشهور لا بالدقائق،
 *     وإعادة جلبها مع كل فتح للنموذج تُبطئ الشاشة بلا مقابل.
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
//  الكتابة
// ═══════════════════════════════════════════════════════════

/**
 * ⚠️  إبطال قائمة المنتجات **وخيارات النموذج معًا** بعد أي كتابة.
 *
 *     القائمة وحدها تكفي للحذف والتعديل، لكن المنتج الجديد قد
 *     يكون أول ما يُسنَد إلى فئة، ويبقى عدّاد الشاشة قديمًا.
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
 * ⚠️  حذف ناعم على الخادم — الصف يبقى وتشير إليه الطلبات التاريخية.
 *     ولذلك يقابله `useRestoreProduct` لا حذف نهائي.
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
