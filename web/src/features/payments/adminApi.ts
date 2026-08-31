import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * Payment gateways.
 *
 * ⚠️  `is_active` is **the on/off switch** — its effect is immediate: a disabled
 *     gateway disappears from the customer's options on the next request with
 *     no redeployment. (ADR-15)
 */
export interface PaymentProvider {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  adapter_key: string;
  /** ⚠️  A gateway with a nonexistent adapter fails on the first payment — it is surfaced here. */
  adapter_exists: boolean;
  supported_methods: string[];
  supported_currencies: string[];
  supported_channels: string[];
  min_amount: string | null;
  max_amount: string | null;
  priority: number;
  is_sandbox: boolean;
  is_active: boolean;
  is_configured: boolean;
  /** The names of the configured keys — never their values. */
  credential_keys: string[];
  /**
   * ⚠️  The keys **this adapter** declares it cannot work without — empty for most.
   *
   *     Cash on delivery, cash at the counter, the card terminal and bank
   *     transfer all require none: there is no key to hand a courier.
   */
  required_credentials: string[];
  /** Of those, the ones still missing for the mode the gateway is in. */
  missing_credentials: string[];
  /**
   * ⚠️  **Whether the server will accept enabling it — computed there, not here.**
   *
   *     This screen used to work it out for itself from "are there any stored
   *     credentials?", which is the wrong question. It is true of Paymob and
   *     nonsense for cash on delivery, so disabling cash on delivery hid its own
   *     enable button behind a demand for keys that do not exist — and the only
   *     way back was the Django admin.
   */
  can_enable: boolean;
}

export interface ProviderCredential {
  id: string;
  key: string;
  masked_value: string;
  is_sandbox: boolean;
}

export const listProviders = () =>
  http.get<PaymentProvider[]>('/payments/admin/providers/');

/**
 * ⚠️  Disabling is refused with `409` if it is the last enabled gateway.
 *
 *     A store with no gateway accepts no orders, and the discovery comes
 *     through a customer complaint rather than an alert. And the reason is
 *     recorded in the audit log.
 */
export const toggleProvider = (id: string, isActive: boolean, reason = '') =>
  http.post<PaymentProvider>(`/payments/admin/providers/${id}/toggle/`, {
    is_active: isActive,
    reason,
  });

export const listCredentials = (providerId: string) =>
  http.get<ProviderCredential[]>(`/payments/admin/providers/${providerId}/credentials/`);

/**
 * ⚠️  The value is **written and never read** — not even by the admin.
 *
 *     The response carries `masked_value` only. Returning the key "to check it"
 *     makes one leaked admin session a leak of the entire gateway account.
 */
export const addCredential = (providerId: string, key: string, value: string, isSandbox: boolean) =>
  http.post<ProviderCredential>(`/payments/admin/providers/${providerId}/credentials/`, {
    key,
    value,
    is_sandbox: isSandbox,
  });

// ═══════════════════════════════════════════════════════════
//  Transactions
// ═══════════════════════════════════════════════════════════

export type TransactionStatus =
  | 'PENDING'
  | 'AUTHORIZED'
  | 'CAPTURED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REFUNDED';

/**
 * ⚠️  `provider_response` **is not here** and never will be.
 *
 *     It may carry partial card data or internal gateway codes — and the server
 *     excludes it from every response.
 */
export interface PaymentTransaction {
  id: string;
  reference: string;
  provider: string;
  provider_code: string;
  method: string;
  amount: string;
  currency: string;
  status: TransactionStatus;
  reference_type: string;
  reference_id: string;
  provider_reference: string;
  failure_code: string;
  failure_message: string;
  refunded_amount: string;
  refundable_amount: string;
  authorized_at: string | null;
  captured_at: string | null;
  created_at: string;
}

export interface Refund {
  id: string;
  reference: string;
  amount: string;
  reason: string;
  status: string;
  created_at: string;
}

export const listTransactions = (params: {
  status?: string;
  provider?: string;
  reference_id?: string;
  page?: number;
}) =>
  http.get<PagedResponse<PaymentTransaction>>('/payments/admin/transactions/', {
    params: { ...params },
  });

/**
 * A single transaction in detail.
 *
 * ⚠️  **The failure message is why this endpoint exists.**
 *
 *     The table row says "failed"; and `failure_code` and `failure_message` say
 *     why — "insufficient funds" is not "card declined" is not "gateway
 *     unreachable", and only the third is worth retrying. Without the detail,
 *     support calls the gateway in every case.
 */
export function useTransaction(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'transaction', id],
    queryFn: () => http.get<PaymentTransaction>(`/payments/admin/transactions/${id}/`),
    enabled: id !== null,
  });
}

/**
 * ⚠️  Invalidate the transactions **and the orders together**.
 *
 *     A capture or a refund changes the order's payment status through a signal
 *     on the server; invalidating the transactions list alone leaves the order
 *     screen showing "unpaid" beside a transaction just captured.
 */
function useTransactionMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'transactions'] });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'orders'] });
    },
  });
}

/**
 * Capture an authorised transaction.
 *
 * ⚠️  For cash on delivery: called when the order is **actually** delivered.
 *     Marking it captured before that means phantom revenue in every financial report.
 */
export function useCaptureTransaction() {
  return useTransactionMutation((id: string) =>
    http.post<PaymentTransaction>(`/payments/admin/transactions/${id}/capture/`),
  );
}

/**
 * ⚠️  The reason is mandatory, and an empty amount means **the full remainder**.
 *
 *     The server refuses anything exceeding `refundable_amount` — and refunding
 *     more than was paid is an accounting error that is not easily corrected.
 */
export function useRefundTransaction() {
  return useTransactionMutation(
    ({ id, amount, reason }: { id: string; amount?: string; reason: string }) =>
      http.post<Refund>(`/payments/admin/transactions/${id}/refund/`, {
        ...(amount ? { amount } : {}),
        reason,
      }),
  );
}

// ═══════════════════════════════════════════════════════════
//  Gateway management — creation, editing and ordering
// ═══════════════════════════════════════════════════════════

export interface AdapterOptions {
  /** The names of the adapters registered in the code — the admin chooses from them */
  adapters: string[];
  /**
   * ⚠️  What each adapter **requires**, so the form can say so before the gateway
   *     is created rather than after it refuses to enable.
   */
  adapter_requirements: Record<string, string[]>;
  methods: { value: string; label_ar: string }[];
}

/**
 * ⚠️  The adapter is **code, not data**: adding a gateway means choosing an
 *     existing adapter, not typing a name. And an unregistered name produces a
 *     gateway that fails on the first purchase.
 */
export function useAdapterOptions(enabled = true) {
  return useQuery({
    queryKey: ['admin', 'payment-adapters'],
    queryFn: () => http.get<AdapterOptions>('/payments/admin/adapters/'),
    staleTime: 30 * 60 * 1000,
    enabled,
  });
}

/**
 * ⚠️  The key is `['admin', 'payment-providers']` — **the one the lists actually use.**
 *
 *     It read `['admin', 'payments']`, which prefix-matches nothing: the gateway
 *     list, the dashboard tile and the transactions panel all subscribe under
 *     `payment-providers`. So creating, deleting and reordering a gateway
 *     succeeded on the server and refreshed no screen — the row stayed where it
 *     was until the page was reloaded by hand, which reads as "the button did
 *     nothing" and invites a second press.
 */
export const PROVIDERS_KEY = ['admin', 'payment-providers'] as const;

export const credentialsKey = (providerId: string) =>
  [...PROVIDERS_KEY, providerId, 'credentials'] as const;

function useProviderMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROVIDERS_KEY }),
  });
}

export function useSaveProvider() {
  return useProviderMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    id
      ? http.patch<PaymentProvider>(`/payments/admin/providers/${id}/`, body)
      : http.post<PaymentProvider>('/payments/admin/providers/', body),
  );
}

/**
 * ⚠️  The server answers 409 for a gateway with transactions.
 *
 *     Deleting it leaves historical transactions with no reference, so every
 *     past financial report breaks. Disabling is the alternative.
 */
export function useDeleteProvider() {
  return useProviderMutation((id: string) =>
    http.delete<void>(`/payments/admin/providers/${id}/`),
  );
}

/**
 * Reordering the priority.
 *
 * ⚠️  The order determines **which gateway is tried first** when more than one
 *     suits the same operation — the decision that steers the money to a
 *     particular gateway.
 */
export function useReorderProviders() {
  return useProviderMutation((order: string[]) =>
    http.post<PaymentProvider[]>('/payments/admin/providers/reorder/', { order }),
  );
}

/**
 * The keys stored for one gateway — names and masked values, never the values.
 *
 * ⚠️  Fetched **only when the section is open**.
 *
 *     A page showing six gateways would otherwise fire six requests for panels
 *     nobody expanded, on a screen already loading the gateway list itself.
 */
export function useProviderCredentials(providerId: string, enabled: boolean) {
  return useQuery({
    queryKey: credentialsKey(providerId),
    queryFn: () => listCredentials(providerId),
    enabled,
  });
}

/**
 * ⚠️  Invalidates **both** the credential list and the gateway list.
 *
 *     Adding the last missing key is what flips `can_enable` from false to true,
 *     and that flag lives on the gateway row, not on the credential. Refreshing
 *     only the keys leaves the card still saying "missing credentials" beside the
 *     key just entered — and the admin adds it a second time.
 */
export function useAddCredential(providerId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ key, value, isSandbox }: { key: string; value: string; isSandbox: boolean }) =>
      addCredential(providerId, key, value, isSandbox),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: credentialsKey(providerId) });
      void queryClient.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}

export function useDeleteCredential(providerId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (credentialId: string) =>
      http.delete<void>(`/payments/admin/providers/${providerId}/credentials/${credentialId}/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: credentialsKey(providerId) });
      void queryClient.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}
