/**
 * واجهة الكتالوج.
 *
 * ⚠️  مسارات نسبية فقط. `shared/http` يبني العنوان الكامل من
 *     `VITE_API_BASE_URL` — وقاعدة ESLint ترفض أي عنوان مطلق هنا.
 */

import { http } from '@/shared/http';

import type {
  Availability,
  CategoryBrief,
  CursorPage,
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
