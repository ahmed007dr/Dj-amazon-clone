/**
 * واجهة الكتالوج.
 *
 * ⚠️  مسارات نسبية فقط. `shared/http` يبني العنوان الكامل من
 *     `VITE_API_BASE_URL` — وقاعدة ESLint ترفض أي عنوان مطلق هنا.
 */

import { http } from '@/shared/http';

import type {
  Availability,
  Brand,
  CategoryBrief,
  CategoryDetail,
  CursorPage,
  Manufacturer,
  ProductDetail,
  ProductListItem,
  ProductQuery,
  Review,
} from './types';

export const listProducts = (params: ProductQuery, signal?: AbortSignal) =>
  http.get<CursorPage<ProductListItem>>('/catalog/products/', {
    params: { ...params },
    ...(signal ? { signal } : {}),
  });

/** ⚠️  المعرّف `slug` لا UUID — الرابط يجب أن يكون قابلًا للقراءة والمشاركة. (ADR-27) */
export const getProduct = (slug: string) =>
  http.get<ProductDetail>(`/catalog/products/${slug}/`);

export const listCategories = () =>
  http.get<CategoryBrief[] | CursorPage<CategoryBrief>>('/catalog/categories/');

/**
 * توفر مجموعة منتجات — **استعلام واحد مجمّع**.
 *
 * ⚠️  نداء لكل منتج يعيد الـ N+1 إلى قوائم الكتالوج من باب الواجهة
 *     بعد أن أُغلق في الخادم.
 */
export const getAvailability = (productIds: string[]) =>
  http.get<Record<string, Availability>>('/inventory/availability/', {
    params: { products: productIds.join(',') },
  });

export const listProductReviews = (slug: string) =>
  http.get<CursorPage<Review> | Review[]>(`/reviews/products/${slug}/`);

/**
 * تقييم المنتج المجمَّع — **نقطة منفصلة عن قائمة المراجعات**.
 *
 * ⚠️  المتوسط والعدد يظهران في رأس الصفحة قبل أن يفتح أحد قائمة
 *     المراجعات؛ وجلب القائمة كاملة لحساب رقمين يعني تحميل عشرات
 *     النصوص لعرض نجمة.
 */
export const getProductRating = (slug: string) =>
  http.get<{ average: string; count: number }>(`/reviews/products/${slug}/rating/`);

// ── الماركات والمصنّعون والفئات ────────────────────────────
//
// ⚠️  **بلا ترقيم على الخادم** (`pagination_class = None`): مصفوفة
//     مباشرة لا `results`. توقّع الترقيم هنا كان يعطي `undefined`
//     صامتًا وشبكة فارغة.

export const listBrands = (featured?: boolean) =>
  http.get<Brand[]>('/catalog/brands/', {
    params: featured ? { featured: 'true' } : {},
  });

export const getBrand = (slug: string) => http.get<Brand>(`/catalog/brands/${slug}/`);

export const listManufacturers = () => http.get<Manufacturer[]>('/catalog/manufacturers/');

export const getCategory = (slug: string) =>
  http.get<CategoryDetail>(`/catalog/categories/${slug}/`);

/**
 * بحث بالباركود — **لماسح نقطة البيع**.
 *
 * ⚠️  نقطة منفصلة عن البحث النصّي: الماسح يرسل الرقم كاملًا ويجب
 *     أن يعطي الصنف الواحد فورًا لا قائمة يختار منها الكاشير
 *     بينما الطابور ينتظر.
 */
export const getProductByBarcode = (barcode: string) =>
  http.get<ProductDetail>(`/catalog/barcode/${barcode}/`);
