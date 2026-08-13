/**
 * واجهة الكتالوج.
 *
 * ⚠️  مسارات نسبية فقط. `shared/http` يبني العنوان الكامل من
 *     `VITE_API_BASE_URL` — وقاعدة ESLint ترفض أي عنوان مطلق هنا.
 */

import { http } from '@/shared/http';

import type { CategoryBrief, CursorPage, ProductListItem, ProductQuery } from './types';

export const listProducts = (params: ProductQuery, signal?: AbortSignal) =>
  http.get<CursorPage<ProductListItem>>('/catalog/products/', {
    params: { ...params },
    ...(signal ? { signal } : {}),
  });

export const getProduct = (slug: string) =>
  http.get<ProductListItem>(`/catalog/products/${slug}/`);

export const listCategories = () =>
  http.get<CategoryBrief[] | CursorPage<CategoryBrief>>('/catalog/categories/');
