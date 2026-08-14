/**
 * واجهة الطلبات للأدمن.
 *
 * ⚠️  ترقيم **بالصفحات** لا بالمؤشر هنا وحده.
 *
 *     الخادم يكشف `count` لشاشات الأدمن فقط (ADR-32): «صفحة ٥ من
 *     ٤٢» معلومة تشغيلية يحتاجها من يعالج الطلبات، وكشفها للعامة
 *     يعطي المنافس حجم النشاط.
 */

import { http } from '@/shared/http';

import type { OrderDetail, OrderStatus } from './types';

export interface AdminOrder extends OrderDetail {
  customer: string;
  customer_email: string;
  customer_number: string;
  location: string | null;
  created_by: string | null;
  owner_employee: string | null;
  commission_employee: string | null;
  internal_note: string;
}

export interface PagedResponse<T> {
  results: T[];
  count: number;
  page: number;
  pages: number;
  next: string | null;
  previous: string | null;
}

export interface AdminOrderQuery {
  status?: string;
  payment_status?: string;
  channel?: string;
  search?: string;
  page?: number;
}

export const listAdminOrders = (params: AdminOrderQuery) =>
  http.get<PagedResponse<AdminOrder>>('/orders/admin/', { params: { ...params } });

export const getAdminOrder = (id: string) => http.get<AdminOrder>(`/orders/admin/${id}/`);

/**
 * ⚠️  الانتقال غير المسموح يُرفض بـ `409` من **آلة الحالة في الخادم**.
 *
 *     الواجهة تعرض الانتقالات الممكنة لتحسين التجربة، ولا تكرّر
 *     القواعد: قائمة موازية تتباعد عن الحقيقية فيظهر زر يفشل.
 */
export const transitionOrder = (id: string, status: OrderStatus, note = '') =>
  http.post<AdminOrder>(`/orders/admin/${id}/transition/`, { to_status: status, note });

export const completeOrder = (id: string) =>
  http.post<AdminOrder>(`/orders/admin/${id}/complete/`);
