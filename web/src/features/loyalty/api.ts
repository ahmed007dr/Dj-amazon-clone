import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * Loyalty and referrals.
 *
 * ⚠️  **`enabled: false` is a normal response, not an error.**
 *
 *     The system may be disabled entirely, or targeted at a segment that does
 *     not include this account. Treating it as an error makes the frontend show
 *     a fault message to a customer with no fault — the right behaviour is to
 *     hide the section quietly.
 */

// ═══════════════════════════════════════════════════════════
//  Customer
// ═══════════════════════════════════════════════════════════

export interface LoyaltySummary {
  enabled: boolean;
  program?: {
    name_ar: string;
    name_en: string;
    point_value: string;
    currency_per_point: string;
    max_redemption_percent: string;
    redemption_enabled: boolean;
    expiry_months: number;
  };
  balance?: number;
  usable_points?: number;
  tier?: { name_ar: string; name_en: string; multiplier: string } | null;
  next_tier?: {
    name_ar: string;
    name_en: string;
    threshold: string;
    remaining: string;
  } | null;
}

export type PointsKind =
  | 'EARN'
  | 'REDEEM'
  | 'EXPIRE'
  | 'REVERSE'
  | 'REFERRAL'
  | 'ADJUSTMENT'
  | 'DEDUCTION';

export interface PointsEntry {
  id: string;
  kind: PointsKind;
  kind_display: string;
  points: number;
  signed_points: number;
  points_remaining: number;
  expires_on: string | null;
  reference: string;
  note: string;
  order_number: string | null;
  created_at: string;
}

export interface AdminPointsEntry extends PointsEntry {
  customer_name: string;
  recorded_by_name: string;
}

export interface RedemptionQuote {
  allowed: boolean;
  reason: string;
  points: number;
  value: string;
  max_points: number;
}

export interface RedemptionResult {
  coupon_code: string;
  value: string;
  expires_at: string;
  balance: number;
}

export interface ReferralSummary {
  enabled: boolean;
  code?: string;
  program?: {
    name_ar: string;
    name_en: string;
    referrer_points: number;
    referee_points: number;
    min_order_amount: string;
  };
  stats?: { total: number; pending: number; rewarded: number; rejected: number };
}

export function useMyLoyalty() {
  return useQuery({
    queryKey: ['loyalty', 'me'],
    queryFn: () => http.get<LoyaltySummary>('/loyalty/me/'),
    retry: false,
  });
}

export function useMyPoints(page = 1) {
  return useQuery({
    queryKey: ['loyalty', 'me', 'points', page],
    queryFn: () => http.get<PagedResponse<PointsEntry>>('/loyalty/me/points/', { params: { page } }),
    retry: false,
  });
}

export function useMyReferral() {
  return useQuery({
    queryKey: ['loyalty', 'me', 'referral'],
    queryFn: () => http.get<ReferralSummary>('/loyalty/me/referral/'),
    retry: false,
  });
}

/**
 * ⚠️  Pricing goes through the server, not a calculation in the frontend.
 *
 *     Computing it here makes what the customer sees differ from what is
 *     deducted from them on commitment — the worst possible surprise in a
 *     points system.
 */
export function useRedemptionQuote() {
  return useMutation({
    mutationFn: (body: { points: number; order_total: string }) =>
      http.post<RedemptionQuote>('/loyalty/me/redeem/quote/', body),
  });
}

function useLoyaltyMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['loyalty'] }),
  });
}

export function useRedeemPoints() {
  return useLoyaltyMutation((body: { points: number; order_total: string }) =>
    http.post<RedemptionResult>('/loyalty/me/redeem/', body),
  );
}

export function useApplyReferral() {
  return useLoyaltyMutation((code: string) =>
    http.post<{ status: string; detail: string }>('/loyalty/me/referral/apply/', { code }),
  );
}

// ═══════════════════════════════════════════════════════════
//  Admin
// ═══════════════════════════════════════════════════════════

export interface TierLevel {
  id: string;
  program: string;
  code: string;
  name_ar: string;
  name_en: string;
  threshold: string;
  multiplier: string;
  display_order: number;
}

export interface LoyaltyProgram {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  redemption_enabled: boolean;
  account_types: string[];
  customer_segments: string[];
  currency_per_point: string;
  point_value: string;
  earns_on_tax: boolean;
  earns_on_shipping: boolean;
  min_order_amount: string;
  expiry_months: number;
  reverse_on_refund: boolean;
  max_redemption_percent: string;
  note: string;
  tiers: TierLevel[];
}

export interface ReferralProgram {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  is_active: boolean;
  account_types: string[];
  referrer_points: number;
  referee_points: number;
  max_referrals_per_user: number;
  min_order_amount: string;
}

export interface Referral {
  id: string;
  status: 'PENDING' | 'REWARDED' | 'REJECTED';
  status_display: string;
  referrer_name: string;
  referee_name: string;
  rewarded_at: string | null;
  rejection_reason: string;
  created_at: string;
}

export interface LoyaltyOverview {
  liability: { points: number; value: string };
  active_programs: number;
  active_referral_programs: number;
  members: number;
}

export interface TargetingOption {
  value: string;
  label: string;
}

export interface TargetingOptions {
  account_types: TargetingOption[];
  customer_segments: TargetingOption[];
}

export function useLoyaltyOverview() {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'overview'],
    queryFn: () => http.get<LoyaltyOverview>('/loyalty/admin/overview/'),
  });
}

/**
 * ⚠️  The targeting options come from the server, not a list written here.
 *
 *     Duplicating them in the frontend makes adding an account type need two
 *     edits; and forgetting one produces targeting that matches nobody with no
 *     error message.
 */
export function useTargetingOptions() {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'targeting'],
    queryFn: () => http.get<TargetingOptions>('/loyalty/admin/targeting/'),
    staleTime: 60 * 60 * 1000,
  });
}

export function useLoyaltyPrograms() {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'programs'],
    queryFn: () => http.get<PagedResponse<LoyaltyProgram>>('/loyalty/admin/programs/'),
  });
}

export function useReferralPrograms() {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'referral-programs'],
    queryFn: () => http.get<PagedResponse<ReferralProgram>>('/loyalty/admin/referral-programs/'),
  });
}

export function useAdminPoints(filters: { customer?: string; kind?: string; page?: number }) {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'points', filters],
    queryFn: () =>
      http.get<PagedResponse<AdminPointsEntry>>('/loyalty/admin/points/', { params: { ...filters } }),
  });
}

export function useAdminReferrals(status?: string) {
  return useQuery({
    queryKey: ['loyalty', 'admin', 'referrals', status ?? ''],
    queryFn: () =>
      http.get<PagedResponse<Referral>>('/loyalty/admin/referrals/', { params: { status } }),
  });
}

export interface CustomerLookupRow {
  id: string;
  customer_number: string;
  name: string;
  email: string;
  segment: string;
  balance: number;
  usable_points: number;
  covered: boolean;
}

/**
 * ⚠️  The minimum is two characters — and the server enforces it too.
 *
 *     One character matches almost every customer: a list, not a search, and a
 *     call fetching a full page with every keystroke.
 */
export function useCustomerLookup(search: string) {
  const term = search.trim();

  return useQuery({
    queryKey: ['loyalty', 'admin', 'customer-lookup', term],
    queryFn: () =>
      http.get<CustomerLookupRow[]>('/loyalty/admin/customers/', { params: { search: term } }),
    enabled: term.length >= 2,
  });
}

export function useSaveProgram() {
  return useLoyaltyMutation(({ id, ...body }: Partial<LoyaltyProgram> & { id?: string }) =>
    id
      ? http.patch<LoyaltyProgram>(`/loyalty/admin/programs/${id}/`, body)
      : http.post<LoyaltyProgram>('/loyalty/admin/programs/', body),
  );
}

export function useSaveReferralProgram() {
  return useLoyaltyMutation(({ id, ...body }: Partial<ReferralProgram> & { id?: string }) =>
    id
      ? http.patch<ReferralProgram>(`/loyalty/admin/referral-programs/${id}/`, body)
      : http.post<ReferralProgram>('/loyalty/admin/referral-programs/', body),
  );
}

export function useSaveTier() {
  return useLoyaltyMutation(({ id, ...body }: Partial<TierLevel> & { id?: string }) =>
    id
      ? http.patch<TierLevel>(`/loyalty/admin/tiers/${id}/`, body)
      : http.post<TierLevel>('/loyalty/admin/tiers/', body),
  );
}

export function useDeleteTier() {
  return useLoyaltyMutation((id: string) => http.delete<void>(`/loyalty/admin/tiers/${id}/`));
}

export function useDeleteProgram() {
  return useLoyaltyMutation((id: string) =>
    http.delete<void>(`/loyalty/admin/programs/${id}/`),
  );
}

export function useDeleteReferralProgram() {
  return useLoyaltyMutation((id: string) =>
    http.delete<void>(`/loyalty/admin/referral-programs/${id}/`),
  );
}

/** ⚠️  Safe to repeat: it touches only batches whose date has passed today. */
export function useExpirePoints() {
  return useLoyaltyMutation(() =>
    http.post<{ batches: number; points: number }>('/loyalty/admin/expire/', {}),
  );
}

export function useAdjustPoints() {
  return useLoyaltyMutation(
    ({ customer, ...body }: { customer: string; points: number; reason: string }) =>
      http.post<{ entry: AdminPointsEntry; balance: number }>(
        `/loyalty/admin/customers/${customer}/adjust/`,
        body,
      ),
  );
}
