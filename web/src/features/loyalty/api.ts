import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * الولاء والإحالة.
 *
 * ⚠️  **`enabled: false` ردٌّ عادي لا خطأ.**
 *
 *     النظام قد يكون موقوفًا كليًا أو موجَّهًا لفئة لا تشمل هذا
 *     الحساب. معاملته كخطأ تجعل الواجهة تعرض رسالة عطل لعميل لا
 *     عطل عنده — والصحيح أن تُخفي القسم بهدوء.
 */

// ═══════════════════════════════════════════════════════════
//  العميل
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
 * ⚠️  التسعير يمرّ بالخادم لا بحساب في الواجهة.
 *
 *     حسابه هنا يجعل ما يراه العميل يخالف ما يُخصم منه عند
 *     الالتزام — وهي أسوأ مفاجأة ممكنة في نظام نقاط.
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
//  الأدمن
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
 * ⚠️  خيارات الاستهداف من الخادم لا من قائمة مكتوبة هنا.
 *
 *     تكرارها في الواجهة يجعل إضافة نوع حساب تحتاج تعديلين؛
 *     ونسيان أحدهما ينتج استهدافًا لا يطابق أحدًا بلا رسالة خطأ.
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
 * ⚠️  الحد الأدنى حرفان — والخادم يفرضه أيضًا.
 *
 *     حرف واحد يطابق كل العملاء تقريبًا: قائمة لا بحث، ونداء
 *     يجلب صفحة كاملة مع كل ضغطة مفتاح.
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

/** ⚠️  آمنة التكرار: لا تمسّ إلا دفعات تجاوز تاريخها اليوم. */
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
