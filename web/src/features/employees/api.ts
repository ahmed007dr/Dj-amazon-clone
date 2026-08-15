import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import type { OrderListItem } from '@/features/orders/types';
import { http } from '@/shared/http';

/**
 * بوابة الموظفين.
 *
 * ⚠️  **نقاط المندوب بلا معرّف موظف — «أنا وعملائي».**
 *
 *     الخادم يشتقّ الملف من التوكن ويصفّي كل استعلام بإسناده.
 *     تمرير معرّف هنا كان يفتح الباب لقراءة عملاء زميل بتغيير
 *     رقم — وهي بيانات المنافسة الداخلية بين المندوبين.
 */

export interface EmployeeProfile {
  id: string;
  employee_number: string;
  full_name: string;
  email: string;
  role: string;
  role_name_ar: string;
  role_name_en: string;
  manager: string | null;
  manager_name: string | null;
  phone_extension: string;
  hired_on: string | null;
  is_active: boolean;
  customers_count: number;
}

export interface MonthRow {
  month: string;
  orders: number;
  gross: string;
  returns: string;
  net: string;
}

export interface Dashboard {
  employee_number: string;
  full_name: string;
  role: string;
  start: string;
  end: string;
  orders_count: number;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  average_order: string;
  customers_count: number;
  new_customers: number;
  /**
   * ⚠️  **بلا هدف ولا عمولة — والغياب مقصود.**
   *
   *     `targets` و`commissions` فوق `employees` في طبقات الخادم.
   *     حقل `target` هنا كان يعود `null` دائمًا فيُقرأ «لا هدف»
   *     بدل «اسأل `/targets/me/`». اللوحة تُركَّب من ثلاث نقاط.
   */
  history: MonthRow[];
}

export interface AssignedCustomer {
  id: string;
  customer_number: string;
  display_name: string;
  phone: string;
  email: string;
  segment: string;
  total_orders: number;
  total_spent: string;
  last_order_at: string | null;
}

export interface Assignment {
  id: string;
  customer: string;
  customer_number: string;
  employee: string;
  employee_number: string;
  employee_name: string;
  status: 'ACTIVE' | 'ENDED';
  started_at: string;
  ended_at: string | null;
  note: string;
}

// ── بوابة المندوب ──────────────────────────────────────────

export function useMyEmployeeProfile() {
  return useQuery({
    queryKey: ['employees', 'me'],
    queryFn: () => http.get<EmployeeProfile>('/employees/me/'),
    retry: false,
  });
}

export function useDashboard(period: { start?: string; end?: string }) {
  return useQuery({
    queryKey: ['employees', 'dashboard', period],
    queryFn: () => http.get<Dashboard>('/employees/dashboard/', { params: { ...period } }),
    retry: false,
  });
}

export function useMyCustomers(search: string, page: number) {
  return useQuery({
    queryKey: ['employees', 'customers', search, page],
    queryFn: () =>
      http.get<PagedResponse<AssignedCustomer>>('/employees/customers/', {
        params: { ...(search ? { search } : {}), page },
      }),
    retry: false,
  });
}

export function useCustomerOrders(customerId: string | null) {
  return useQuery({
    queryKey: ['employees', 'customer-orders', customerId],
    queryFn: () => http.get<OrderListItem[]>(`/employees/customers/${customerId}/orders/`),
    enabled: customerId !== null,
    retry: false,
  });
}

export interface OrderLineInput {
  product: string;
  quantity: number;
}

export function useCreateOrderForCustomer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: {
      customer: string;
      lines: OrderLineInput[];
      payment_method: string;
      address_id?: string;
      address?: Record<string, string>;
      shipping_method_code?: string;
      customer_note?: string;
    }) => http.post<{ id: string; number: string }>('/employees/orders/', body),
    onSuccess: () => {
      // ⚠️  الطلب الجديد يغيّر لوحة الأداء وقائمة العملاء معًا.
      void queryClient.invalidateQueries({ queryKey: ['employees'] });
    },
  });
}

// ── الأدمن ─────────────────────────────────────────────────

export interface StaffFilters {
  role?: string;
  active?: string;
  search?: string;
  page?: number;
}

export function useAdminStaff(filters: StaffFilters) {
  return useQuery({
    queryKey: ['employees', 'admin', 'staff', filters],
    queryFn: () =>
      http.get<PagedResponse<EmployeeProfile>>('/employees/admin/staff/', {
        params: { ...filters },
      }),
  });
}

export function useUnassignedCustomers(page: number) {
  return useQuery({
    queryKey: ['employees', 'admin', 'unassigned', page],
    queryFn: () =>
      http.get<PagedResponse<AssignedCustomer>>('/employees/admin/unassigned/', {
        params: { page },
      }),
  });
}

export function useAssignCustomer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: { customer: string; employee: string; note?: string }) =>
      http.post<Assignment>('/employees/admin/assignments/assign/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] });
    },
  });
}

export function useEmployeePerformance(id: string | null) {
  return useQuery({
    queryKey: ['employees', 'admin', 'performance', id],
    queryFn: () => http.get<Dashboard>(`/employees/admin/staff/${id}/performance/`),
    enabled: id !== null,
  });
}
