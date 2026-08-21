import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';

/**
 * Assorted reference settings that used to be managed from the Django panel alone:
 * stock locations · expense categories · access policies.
 *
 * ⚠️  **Three different domains in one file** — and the grouping is in the
 *     frontend layer, not on the server: each stays in its own domain there,
 *     and what unites them is that they are configured in the same session at setup.
 */

export interface StockLocation {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  kind: string;
  governorate: string;
  phone: string;
  is_default: boolean;
  /** ⚠️  Quarantine is not sellable — and damaged goods are not shown in the store. */
  is_sellable: boolean;
  is_active: boolean;
}

export interface ExpenseCategory {
  id: string;
  code: string;
  parent: string | null;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  display_order: number;
  expense_count: number;
}

export interface AccessPolicy {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  level: string;
  allowed_account_types: string[];
  requires_verification: boolean;
  required_permission: string;
  denial_message_ar: string;
  denial_message_en: string;
  is_default: boolean;
  is_active: boolean;
}

const LOCATIONS = ['settings', 'locations'] as const;
const EXPENSE_CATEGORIES = ['settings', 'expense-categories'] as const;
const POLICIES = ['settings', 'policies'] as const;

function useSettingsMutation<TArgs, TResult>(
  run: (args: TArgs) => Promise<TResult>,
  extra: readonly string[][] = [],
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
      for (const key of extra) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

// ── Stock locations ───────────────────────────────────────

export function useStockLocations() {
  return useQuery({
    queryKey: LOCATIONS,
    queryFn: () => http.get<StockLocation[]>('/inventory/locations/'),
  });
}

/**
 * ⚠️  Invalidate the inventory tree with it: the movement forms choose the
 *     location from this list, and a new location must appear in it immediately.
 */
export function useSaveLocation() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<StockLocation>(`/inventory/locations/${id}/`, body)
        : http.post<StockLocation>('/inventory/locations/', body),
    [['inventory']],
  );
}

export function useDeleteLocation() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/inventory/locations/${id}/`),
    [['inventory']],
  );
}

// ── Expense categories ────────────────────────────────────

export function useExpenseCategories() {
  return useQuery({
    queryKey: EXPENSE_CATEGORIES,
    queryFn: () => http.get<ExpenseCategory[]>('/finance/categories/'),
  });
}

export function useSaveExpenseCategory() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<ExpenseCategory>(`/finance/categories/${id}/`, body)
        : http.post<ExpenseCategory>('/finance/categories/', body),
    [['finance']],
  );
}

export function useDeleteExpenseCategory() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/finance/categories/${id}/`),
    [['finance']],
  );
}

// ── Access policies ───────────────────────────────────────

export function useAccessPolicies() {
  return useQuery({
    queryKey: POLICIES,
    queryFn: () => http.get<AccessPolicy[]>('/access/policies/'),
  });
}

/**
 * ⚠️  Invalidate the product form options with it.
 *
 *     A new policy is chosen from inside the product form ("who sees this
 *     product?") — and without the invalidation the admin creates it and then
 *     cannot find it exactly where they need it.
 */
export function useSavePolicy() {
  return useSettingsMutation(
    ({ id, body }: { id?: string; body: Record<string, unknown> }) =>
      id
        ? http.patch<AccessPolicy>(`/access/policies/${id}/`, body)
        : http.post<AccessPolicy>('/access/policies/', body),
    [['admin', 'product-options']],
  );
}

export function useDeletePolicy() {
  return useSettingsMutation(
    (id: string) => http.delete<void>(`/access/policies/${id}/`),
    [['admin', 'product-options']],
  );
}

/**
 * The "who sees what" matrix.
 *
 * ⚠️  **Computed from the evaluation engine itself — not from reading the fields.**
 *
 *     Deriving the outcome in the frontend from `allowed_account_types` alone
 *     ignores `requires_verification` and `required_permission`, so the matrix
 *     shows access permitted where the system actually blocks it. And a matrix
 *     that lies is worse than no matrix: configuration decisions are built on it.
 */
export interface AccessMatrixCell {
  unverified: boolean;
  verified?: boolean;
}

export interface AccessMatrix {
  account_types: string[];
  policies: { policy: AccessPolicy; access: Record<string, AccessMatrixCell> }[];
}

export function useAccessMatrix() {
  return useQuery({
    queryKey: ['access', 'matrix'],
    queryFn: () => http.get<AccessMatrix>('/access/matrix/'),
  });
}

export interface PreviewStatus {
  active: boolean;
  account_type?: string;
  verified?: boolean;
  note?: string;
}

/**
 * ⚠️  Preview mode **must be announced**.
 *
 *     An admin who forgets they are browsing through a student's eyes reads an
 *     incomplete catalogue and assumes their products have disappeared — and
 *     then reports a fault that does not exist.
 */
export function usePreviewStatus() {
  return useQuery({
    queryKey: ['access', 'preview-status'],
    queryFn: () => http.get<PreviewStatus>('/access/preview-status/'),
    retry: false,
  });
}
