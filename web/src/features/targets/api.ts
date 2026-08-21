import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * Targets and commissions.
 *
 * ⚠️  **The rep's dashboard is composed from three endpoints, not one.**
 *
 *     `employees` sits below `targets` and `commissions` in the server's layer
 *     order, so no single endpoint gathers all three. And composing here is
 *     three small parallel queries — cheaper than breaking the domain boundaries.
 */

export type TargetStatus = 'DRAFT' | 'ACTIVE' | 'CLOSED';

export interface MonthlyTarget {
  id: string;
  employee: string;
  employee_number: string;
  employee_name: string;
  year: number;
  month: number;
  target_type: string;
  target_value: string;
  minimum_achievement_percent: string;
  status: TargetStatus;
  note: string;
  achieved_value: string | null;
  achievement_percent: string | null;
  closed_at: string | null;
}

export interface MyTarget {
  target: MonthlyTarget;
  achieved_value: string;
  achievement_percent: string;
  meets_minimum: boolean;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  gross_profit: string;
  orders_count: number;
  customers_count: number;
}

export type CommissionStatus = 'CALCULATED' | 'APPROVED' | 'PAID' | 'REJECTED';

export interface CommissionRecord {
  id: string;
  employee_number: string;
  employee_name: string;
  year: number;
  month: number;
  orders_count: number;
  gross_sales: string;
  returns_total: string;
  net_sales: string;
  cost_total: string;
  gross_profit: string;
  target_value: string;
  achieved_value: string;
  achievement_percent: string;
  scheme_code: string;
  base: 'NET_SALES' | 'GROSS_PROFIT';
  base_amount: string;
  tier_label: string;
  rate: string;
  amount: string;
  status: CommissionStatus;
  note: string;
  calculated_at: string;
  approved_at: string | null;
}

/** ⚠️  `null` when there is no target — a normal state at the start of the month, not an error. */
export function useMyTarget() {
  return useQuery({
    queryKey: ['targets', 'me'],
    queryFn: () => http.get<MyTarget | null>('/targets/me/'),
    retry: false,
  });
}

export function useMyCommissions() {
  return useQuery({
    queryKey: ['commissions', 'me'],
    queryFn: () => http.get<PagedResponse<CommissionRecord>>('/commissions/me/'),
    retry: false,
  });
}

/**
 * The commission explanation **for the admin** — a different endpoint from the rep's.
 *
 * ⚠️  The rep's path reads their own commission alone (`/commissions/me/…`);
 *     the admin's path reads any record. Using the first for a row in the
 *     admin's table answered 404 for every employee except the admin themselves.
 */
export function useAdminCommissionExplain(id: string | null) {
  return useQuery({
    queryKey: ['commissions', 'admin', 'explain', id],
    queryFn: () => http.get<Record<string, string | number>>(`/commissions/admin/${id}/explain/`),
    enabled: id !== null,
  });
}

export function useCommissionExplain(id: string | null) {
  return useQuery({
    queryKey: ['commissions', 'explain', id],
    queryFn: () => http.get<Record<string, string>>(`/commissions/me/${id}/explain/`),
    enabled: id !== null,
  });
}

// ── Admin ─────────────────────────────────────────────────

export interface TargetFilters {
  year?: number;
  month?: number;
  employee?: string;
  status?: string;
  page?: number;
}

export function useAdminTargets(filters: TargetFilters) {
  return useQuery({
    queryKey: ['targets', 'admin', filters],
    queryFn: () =>
      http.get<PagedResponse<MonthlyTarget>>('/targets/admin/', { params: { ...filters } }),
  });
}

export function useAdminCommissions(filters: TargetFilters) {
  return useQuery({
    queryKey: ['commissions', 'admin', filters],
    queryFn: () =>
      http.get<PagedResponse<CommissionRecord>>('/commissions/admin/', {
        params: { ...filters },
      }),
  });
}

/**
 * ⚠️  Invalidate both trees together after any write.
 *
 *     Closing a target changes its commission, and computing a commission reads
 *     its target. Invalidating one leaves the screen showing two figures from
 *     two different moments.
 */
function useTargetMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['targets'] });
      void queryClient.invalidateQueries({ queryKey: ['commissions'] });
    },
  });
}

export function useCreateTarget() {
  return useTargetMutation((body: Record<string, unknown>) =>
    http.post<MonthlyTarget>('/targets/admin/', body),
  );
}

export function useActivateTarget() {
  return useTargetMutation((id: string) =>
    http.post<MonthlyTarget>(`/targets/admin/${id}/activate/`, {}),
  );
}

export function useCloseTarget() {
  return useTargetMutation((id: string) =>
    http.post<MonthlyTarget>(`/targets/admin/${id}/close/`, {}),
  );
}

export function useCalculateCommissions() {
  return useTargetMutation((body: { year: number; month: number }) =>
    http.post<{ calculated: number; skipped: { employee: string; reason: string }[] }>(
      '/commissions/admin/calculate/',
      body,
    ),
  );
}

export function useCommissionDecision() {
  return useTargetMutation(
    ({ id, decision, reason }: { id: string; decision: string; reason?: string }) =>
      http.post<CommissionRecord>(`/commissions/admin/${id}/decision/`, { decision, reason }),
  );
}

/**
 * Editing a target before it is activated.
 *
 * ⚠️  An active target is what performance is measured against from the moment
 *     it is activated; and editing its value afterwards rewrites a standard the
 *     rep was already working to. The server guards that, and the frontend
 *     hides the button on an active one.
 */
export function useUpdateTarget() {
  return useTargetMutation(({ id, body }: { id: string; body: Record<string, unknown> }) =>
    http.patch<MonthlyTarget>(`/targets/admin/${id}/`, body),
  );
}

export interface BulkTargetRow {
  employee: string;
  target_value: string;
  target_type?: string;
  minimum_achievement_percent?: string;
  note?: string;
}

/**
 * A team's targets in one batch.
 *
 * ⚠️  **Existing ones are skipped, not overwritten.**
 *
 *     Re-running the batch after adding a new employee must create their target
 *     alone — and overwriting the existing ones erases targets edited by hand
 *     after the first batch.
 */
export function useBulkTargets() {
  return useTargetMutation(
    (body: { year: number; month: number; rows: BulkTargetRow[] }) =>
      http.post<{ created: number }>('/targets/admin/bulk/', body),
  );
}

// ── Commission rules ──────────────────────────────────────

export interface CommissionTier {
  id: string;
  min_achievement_percent: string;
  rate_percent: string;
}

export interface CommissionScheme {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  /** What the rate is computed on: sales or profit */
  base: string;
  role: string | null;
  role_name: string | null;
  is_active: boolean;
  note: string;
  tiers: CommissionTier[];
}

export function useCommissionSchemes(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'commission-schemes'],
    queryFn: () => http.get<CommissionScheme[]>('/commissions/admin/schemes/'),
    enabled,
  });
}

/**
 * ⚠️  **Commission rules are data, not code**: "3% above 100% achievement" is a
 *     management decision that changes every season, and fixing it in code
 *     makes editing it a deployment.
 */
export function useCreateScheme() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      http.post<CommissionScheme>('/commissions/admin/schemes/', body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['admin', 'commission-schemes'] }),
  });
}
