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

// ═══════════════════════════════════════════════════════════
//  الأدوار وتعديل الملفات
// ═══════════════════════════════════════════════════════════

export interface EmployeeRole {
  id: string;
  code: string;
  kind: string;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  permission_count: number;
  /** ⚠️  بصيغة `app_label.codename` لا معرّفات رقمية: الأرقام
   *     تختلف بين التطوير والإنتاج فتمنح غير ما اختاره الأدمن. */
  permissions: string[];
}

export interface PermissionOption {
  code: string;
  label_ar: string;
  label_en: string;
}

export interface PermissionGroup {
  key: string;
  label_ar: string;
  label_en: string;
  permissions: PermissionOption[];
}

/**
 * دليل الصلاحيات — **مُنتقى لا خام**.
 *
 * ⚠️  جدول Django يحمل مئتي صلاحية آلية بأسماء تقنية بينها
 *     `delete_user`. عرضه كما هو يجعل الشاشة غير قابلة للاستعمال
 *     ويجعل منح الخطير سهوًا بضغطة.
 */
export function usePermissionCatalogue(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'permission-catalogue'],
    queryFn: () => http.get<PermissionGroup[]>('/employees/admin/permissions/'),
    enabled,
    staleTime: 60 * 60 * 1000,
  });
}

export function useUpdateRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, ...body }: Partial<EmployeeRole> & { id: string }) =>
      http.patch<EmployeeRole>(`/employees/admin/roles/${id}/`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'employee-roles'] });
    },
  });
}

export function useEmployeeRoles(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'employee-roles'],
    queryFn: () => http.get<EmployeeRole[]>('/employees/admin/roles/'),
    enabled,
  });
}

function useStaffMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'staff'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'employee-roles'] });
    },
  });
}

/**
 * ⚠️  **الصلاحيات على الدور لا على الشخص.**
 *
 *     منحها فردًا يجعل كل موظف جديد يحتاج ضبطًا يدويًا، وأول
 *     منسيّ يبقى بلا صلاحية أو بأكثر مما يجب. ولذلك تُنشأ الأدوار
 *     هنا وتُسنَد الصلاحيات إليها.
 */
export function useCreateRole() {
  return useStaffMutation((body: Record<string, unknown>) =>
    http.post<EmployeeRole>('/employees/admin/roles/', body),
  );
}

export function useUpdateEmployee() {
  return useStaffMutation(({ id, body }: { id: string; body: Record<string, unknown> }) =>
    http.patch(`/employees/admin/staff/${id}/`, body),
  );
}

/**
 * إنهاء إسناد عميل.
 *
 * ⚠️  الإسناد كان يُنشأ ولا يُنهى: مندوب يترك العمل وعملاؤه معلّقون
 *     به — فلا يظهرون لأحد ولا يُسنَدون لغيره.
 */
export function useEndAssignment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (customerId: string) =>
      http.post(`/employees/admin/assignments/${customerId}/end/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'staff'] });
      void queryClient.invalidateQueries({ queryKey: ['employees'] });
    },
  });
}

// ═══════════════════════════════════════════════════════════
//  سجل الإسناد
// ═══════════════════════════════════════════════════════════

export interface CustomerAssignment {
  id: string;
  customer: string;
  customer_number: string;
  employee: string;
  employee_number: string;
  employee_name: string;
  status: 'ACTIVE' | 'ENDED' | 'TRANSFERRED';
  started_at: string;
  ended_at: string | null;
}

/**
 * من أُسند إلى من — **وتاريخ ذلك**.
 *
 * ⚠️  **العمولة تتبع الإسناد، فالتاريخ مالٌ لا سجل.**
 *
 *     «هذا العميل كان لي في مارس» دعوى تُحسم بهذا الجدول وحده.
 *     شاشة الموظفين تعرض العدد الحالي؛ والعدد لا يقول متى انتقل
 *     العميل ولا من كان قبله.
 *
 * ⚠️  و**المنتهي مُدرَج**: قصر القائمة على النشط يجعل السؤال
 *     الوحيد الذي تُفتح لأجله بلا جواب.
 */
export function useAssignments(params: {
  employee?: string;
  customer?: string;
  active?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ['employees', 'admin', 'assignments', params],
    queryFn: () =>
      http.get<PagedResponse<CustomerAssignment>>('/employees/admin/assignments/', {
        params: { ...params },
      }),
  });
}
