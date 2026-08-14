import { http } from '@/shared/http';
import type { PagedResponse } from '@/features/orders/adminApi';

import type { ProductDetail } from './types';

/**
 * ⚠️  المنتج المحذوف ناعمًا **يبقى مرئيًا للأدمن** بعلم `include_deleted`.
 *
 *     الحذف الناعم بلا طريقة لرؤية المحذوف يجعله حذفًا نهائيًا من
 *     منظور المستخدم — وأول سؤال بعد حذف بالخطأ هو «أين ذهب؟».
 */
export interface AdminProduct extends ProductDetail {
  is_active: boolean;
  deleted_at: string | null;
  tax_class: string | null;
  access_policy: string | null;
  published_at: string | null;
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
