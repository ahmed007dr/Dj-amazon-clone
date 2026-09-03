/**
 * The orders API for the admin.
 *
 * ⚠️  **Page** pagination rather than cursor, here alone.
 *
 *     The server exposes `count` for admin screens only (ADR-32): "page 5 of
 *     42" is operational information whoever processes orders needs, and
 *     exposing it publicly gives a competitor the size of the business.
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
 * ⚠️  A disallowed transition is refused with `409` by **the state machine on the server**.
 *
 *     The frontend shows the possible transitions to improve the experience and
 *     does not duplicate the rules: a parallel list drifts from the real one, so
 *     a button appears and fails.
 */
export const transitionOrder = (id: string, status: OrderStatus, note = '') =>
  http.post<AdminOrder>(`/orders/admin/${id}/transition/`, { status, note });

export const completeOrder = (id: string) =>
  http.post<AdminOrder>(`/orders/admin/${id}/complete/`);
