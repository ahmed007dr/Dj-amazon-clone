import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import type { OrderListItem } from '@/features/orders/types';
import { http } from '@/shared/http';

/**
 * The staff portal.
 *
 * ⚠️  **The rep's endpoints carry no employee id — "me and my customers".**
 *
 *     The server derives the profile from the token and filters every query by
 *     their assignment. Passing an id here opened the door to reading a
 *     colleague's customers by changing a number — the data reps compete over internally.
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
   * ⚠️  **No target and no commission — and the absence is deliberate.**
   *
   *     `targets` and `commissions` sit above `employees` in the server's
   *     layers. A `target` field here always returned `null` and read as "no
   *     target" rather than "ask `/targets/me/`". The dashboard is composed from
   *     three endpoints.
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

// ── The rep's portal ──────────────────────────────────────

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
      // ⚠️  A new order changes the performance dashboard and the customer list together.
      void queryClient.invalidateQueries({ queryKey: ['employees'] });
    },
  });
}

// ── Admin ─────────────────────────────────────────────────

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
//  Roles and profile editing
// ═══════════════════════════════════════════════════════════

export interface EmployeeRole {
  id: string;
  code: string;
  kind: string;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  permission_count: number;
  /** ⚠️  In `app_label.codename` form, not numeric ids: the numbers
   *     differ between development and production, so they grant something other than what the admin chose. */
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
 * The permission catalogue — **curated, not raw**.
 *
 * ⚠️  Django's table holds two hundred automatic permissions under technical
 *     names, `delete_user` among them. Showing it as-is makes the screen
 *     unusable and makes granting the dangerous ones by oversight one click away.
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
 * ⚠️  **Permissions sit on the role, not on the person.**
 *
 *     Granting them to an individual makes every new employee need manual
 *     configuration, and the first one forgotten is left with too few
 *     permissions or too many. So roles are created here and the permissions
 *     assigned to them.
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
 * Ending a customer assignment.
 *
 * ⚠️  Assignments were created and never ended: a rep leaves and their customers
 *     stay attached to them — appearing to nobody and assignable to no one else.
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
//  The assignment log
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
 * Who was assigned to whom — **and when**.
 *
 * ⚠️  **Commission follows the assignment, so the history is money, not a record.**
 *
 *     "This customer was mine in March" is a claim settled by this table alone.
 *     The employees screen shows the current count; and a count says neither
 *     when the customer moved nor who had them before.
 *
 * ⚠️  And **the ended ones are included**: restricting the list to the active
 *     ones leaves the only question it is opened for unanswered.
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
