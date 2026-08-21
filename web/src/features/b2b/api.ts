import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * B2B — the credit account.
 *
 * ⚠️  **The customer endpoints carry no id at all.**
 *
 *     `/b2b/account/` means "my own account" — the server derives it from the
 *     token. Passing an id here opened the door to reading a competing
 *     pharmacy's account by changing a number, which is direct commercial
 *     damage rather than a mere privacy breach.
 */

export type CreditStatus = 'NONE' | 'ACTIVE' | 'SUSPENDED';

export interface AccountSummary {
  legal_name: string;
  credit_status: CreditStatus;
  credit_limit: string;
  outstanding: string;
  available: string;
  payment_terms_days: number;
  license_expires_on: string | null;
  license_is_valid: boolean;
  overdue_count: number;
  overdue_total: string;
}

export interface LedgerEntry {
  id: string;
  kind: 'CHARGE' | 'PAYMENT' | 'CREDIT_NOTE' | 'ADJUSTMENT';
  amount: string;
  is_debit: boolean;
  order_number: string | null;
  occurred_on: string;
  due_on: string | null;
  reference: string;
  note: string;
}

export interface AgingBucket {
  label: string;
  amount: string;
}

export interface Statement {
  start: string;
  end: string;
  opening_balance: string;
  closing_balance: string;
  entries: LedgerEntry[];
  aging: AgingBucket[];
}

export interface Invoice {
  id: string;
  number: string;
  order_number: string;
  issued_on: string;
  due_on: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  status: 'ISSUED' | 'PAID' | 'OVERDUE' | 'CANCELLED';
  is_overdue: boolean;
  days_overdue: number;
}

export interface ReorderItem {
  product: string;
  sku: string;
  name_ar: string;
  name_en: string;
  times: number;
  total_quantity: number;
}

export interface BusinessProfile {
  id: string;
  customer_number: string;
  kind: string;
  legal_name: string;
  license_number: string;
  license_expires_on: string | null;
  credit_status: CreditStatus;
  credit_limit: string;
  payment_terms_days: number;
  credit_note: string;
}

// ── The business customer ─────────────────────────────────

export function useMyAccount() {
  return useQuery({
    queryKey: ['b2b', 'account'],
    queryFn: () => http.get<AccountSummary>('/b2b/account/'),
    // ⚠️  No retry on 404: an account with no business profile is a permanent
    //     state until customer service intervenes, and three attempts do not change it.
    retry: false,
  });
}

export function useMyStatement(period: { start?: string; end?: string }) {
  return useQuery({
    queryKey: ['b2b', 'statement', period],
    queryFn: () => http.get<Statement>('/b2b/statement/', { params: { ...period } }),
    retry: false,
  });
}

export function useMyInvoices(openOnly: boolean) {
  return useQuery({
    queryKey: ['b2b', 'invoices', openOnly],
    queryFn: () =>
      http.get<PagedResponse<Invoice>>('/b2b/invoices/', {
        params: openOnly ? { open: 'true' } : {},
      }),
    retry: false,
  });
}

export function useReorderSuggestions() {
  return useQuery({
    queryKey: ['b2b', 'reorder'],
    queryFn: () => http.get<ReorderItem[]>('/b2b/reorder/'),
    retry: false,
  });
}

/** A pre-check — it prevents a refusal after building a whole cart. */
export function useCreditCheck() {
  return useMutation({
    mutationFn: (amount: string) =>
      http.post<{ allowed: boolean; reason: string; available: string }>(
        '/b2b/credit-check/',
        { amount },
      ),
  });
}

export interface CreditCheckoutPayload {
  address_id: string;
  shipping_method_code?: string;
  customer_note?: string;
}

export interface CreditCheckoutResponse {
  order: { id: string; number: string };
  invoice: { number: string; due_on: string };
  available_after: string;
  due_on: string;
}

/**
 * Checkout **on account**.
 *
 * ⚠️  A separate endpoint from `/orders/checkout/` — and the separation is deliberate.
 *
 *     The credit path **accepts no `payment_method` at all**: the endpoint
 *     itself is the method. Accepting the field opened a door to sending "card"
 *     down the credit path, so what was paid in cash got charged to the
 *     customer's account.
 *
 * ⚠️  And the balance and the cart are both invalidated on success: the order
 *     left the cart and was charged against the credit limit at the same moment.
 */
export function useCreditCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreditCheckoutPayload) =>
      http.post<CreditCheckoutResponse>('/b2b/checkout/', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['b2b'] });
      void queryClient.invalidateQueries({ queryKey: ['cart'] });
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
}

// ── Admin ─────────────────────────────────────────────────

export interface BusinessFilters {
  credit_status?: string;
  kind?: string;
  search?: string;
  overdue?: string;
  page?: number;
}

export function useAdminBusinesses(filters: BusinessFilters) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'businesses', filters],
    queryFn: () =>
      http.get<PagedResponse<BusinessProfile>>('/b2b/admin/businesses/', {
        params: { ...filters },
      }),
  });
}

/**
 * A single business account's profile — **for editing, not display alone**.
 *
 * ⚠️  The licence number and its expiry date are edited from here.
 *
 *     An expired licence blocks credit (`license_is_valid`), so a pharmacy that
 *     renewed its licence stays blocked until the date is updated — and no
 *     screen offered any way to update it.
 */
export function useAdminBusiness(id: string | null) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'business', id],
    queryFn: () => http.get<BusinessProfile>(`/b2b/admin/businesses/${id}/`),
    enabled: id !== null,
  });
}

export function useUpdateBusiness() {
  return useCreditMutation(({ id, ...body }: Partial<BusinessProfile> & { id: string }) =>
    http.patch<BusinessProfile>(`/b2b/admin/businesses/${id}/`, body),
  );
}

/** The account movement statement — more detailed than the aggregated statement. */
export function useAdminLedger(id: string | null, page = 1) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'ledger', id, page],
    queryFn: () =>
      http.get<PagedResponse<LedgerEntry>>(`/b2b/admin/businesses/${id}/ledger/`, {
        params: { page },
      }),
    enabled: id !== null,
  });
}

/**
 * My business profile — **read and edited by the customer**.
 *
 * ⚠️  The credit limit and its status are **not edited from here**: the server
 *     ignores what the customer does not own. This screen is for the business's
 *     details, not its money.
 */
export function useMyBusinessProfile() {
  return useQuery({
    queryKey: ['b2b', 'profile'],
    queryFn: () => http.get<BusinessProfile>('/b2b/profile/'),
    retry: false,
  });
}

export function useUpdateMyBusinessProfile() {
  return useCreditMutation((body: Partial<BusinessProfile>) =>
    http.patch<BusinessProfile>('/b2b/profile/', body),
  );
}

export function useAdminStatement(id: string | null) {
  return useQuery({
    queryKey: ['b2b', 'admin', 'statement', id],
    queryFn: () =>
      http.get<Statement & { legal_name: string; credit_limit: string; outstanding: string }>(
        `/b2b/admin/businesses/${id}/statement/`,
      ),
    enabled: id !== null,
  });
}

/**
 * ⚠️  Invalidate the whole `b2b` tree after any write.
 *
 *     Granting credit changes the list, the statement and the customer
 *     dashboard together; invalidating one of them leaves a stale figure beside
 *     the one that changed.
 */
function useCreditMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['b2b'] });
    },
  });
}

export function useGrantCredit() {
  return useCreditMutation(
    ({
      id,
      limit,
      terms_days,
      note,
    }: {
      id: string;
      limit: string;
      terms_days: number;
      note?: string;
    }) => http.post<BusinessProfile>(`/b2b/admin/businesses/${id}/credit/`, {
      limit,
      terms_days,
      note,
    }),
  );
}

export function useSuspendCredit() {
  return useCreditMutation(({ id, reason }: { id: string; reason: string }) =>
    http.post<BusinessProfile>(`/b2b/admin/businesses/${id}/suspend/`, { reason }),
  );
}

export function useRecordPayment() {
  return useCreditMutation(
    ({
      id,
      amount,
      reference,
      note,
    }: {
      id: string;
      amount: string;
      reference?: string;
      note?: string;
    }) => http.post<LedgerEntry>(`/b2b/admin/businesses/${id}/payments/`, {
      amount,
      reference,
      note,
    }),
  );
}
