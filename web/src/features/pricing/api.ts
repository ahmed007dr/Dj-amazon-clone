import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';

/**
 * Pricing and offers.
 *
 * ⚠️  **Every endpoint here is for the admin** — and none has a public counterpart.
 *
 *     The price reaches the customer already computed inside the product, the
 *     cart and the order. And exposing the price lists hands a competitor your
 *     entire pricing structure, while exposing the coupons makes every visitor
 *     try the highest available discount.
 */

export interface PriceList {
  id: string;
  code: string;
  kind: string;
  name_ar: string;
  name_en: string;
  account_types: string[];
  priority: number;
  is_default: boolean;
  is_active: boolean;
  valid_from: string;
  valid_to: string | null;
  is_currently_valid: boolean;
  /** ⚠️  Zero means an enabled list with no prices — its customers see retail. */
  rule_count: number;
}

export interface PriceRule {
  id: string;
  price_list: string;
  product: string;
  product_sku: string;
  product_name: string;
  variant: string | null;
  min_quantity: number;
  unit_price: string;
  is_active: boolean;
}

export interface PriceOverride {
  id: string;
  product: string;
  product_sku: string;
  product_name: string;
  variant: string | null;
  price_list: string | null;
  discount_kind: 'PERCENTAGE' | 'FIXED';
  discount_value: string;
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  is_running: boolean;
}

export interface Coupon {
  id: string;
  code: string;
  name_ar: string;
  name_en: string;
  description_ar: string;
  description_en: string;
  kind: 'PERCENTAGE' | 'FIXED' | 'FREE_SHIPPING';
  value: string;
  max_discount_amount: string | null;
  min_order_amount: string;
  account_types: string[];
  first_order_only: boolean;
  owner: string | null;
  products: string[];
  categories: string[];
  usage_limit: number | null;
  usage_limit_per_user: number;
  usage_count: number;
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  /** ⚠️  Three flags, not one: the admin needs "why does it not work?". */
  is_running: boolean;
  is_expired: boolean;
  is_exhausted: boolean;
}

const KEY = ['admin', 'pricing'] as const;

/**
 * ⚠️  Invalidate **the whole pricing tree and the catalogue with it**.
 *
 *     Changing a price or enabling a discount changes what the customer sees on
 *     the product card immediately. Invalidating the rules list alone leaves
 *     the admin seeing their new price in the panel and the old one in the preview.
 */
function usePricingMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: KEY });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}

// ── Price lists ───────────────────────────────────────────

export function usePriceLists(enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'lists'],
    queryFn: () => http.get<PriceList[]>('/pricing/admin/lists/'),
    enabled,
  });
}

export function useSavePriceList() {
  return usePricingMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    id
      ? http.patch<PriceList>(`/pricing/admin/lists/${id}/`, body)
      : http.post<PriceList>('/pricing/admin/lists/', body),
  );
}

export function useDeletePriceList() {
  return usePricingMutation((id: string) => http.delete<void>(`/pricing/admin/lists/${id}/`));
}

// ── Pricing rules ─────────────────────────────────────────

export function usePriceRules(params: { price_list?: string; search?: string; page?: number }) {
  return useQuery({
    queryKey: [...KEY, 'rules', params],
    queryFn: () =>
      http.get<PagedResponse<PriceRule>>('/pricing/admin/rules/', { params: { ...params } }),
    enabled: Boolean(params.price_list),
  });
}

export function useSavePriceRule() {
  return usePricingMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    id
      ? http.patch<PriceRule>(`/pricing/admin/rules/${id}/`, body)
      : http.post<PriceRule>('/pricing/admin/rules/', body),
  );
}

export function useDeletePriceRule() {
  return usePricingMutation((id: string) => http.delete<void>(`/pricing/admin/rules/${id}/`));
}

// ── Promotional discounts ─────────────────────────────────

export function usePriceOverrides(params: { running?: string; page?: number }, enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'overrides', params],
    queryFn: () =>
      http.get<PagedResponse<PriceOverride>>('/pricing/admin/overrides/', {
        params: { ...params },
      }),
    enabled,
  });
}

export function useSaveOverride() {
  return usePricingMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    id
      ? http.patch<PriceOverride>(`/pricing/admin/overrides/${id}/`, body)
      : http.post<PriceOverride>('/pricing/admin/overrides/', body),
  );
}

export function useDeleteOverride() {
  return usePricingMutation((id: string) =>
    http.delete<void>(`/pricing/admin/overrides/${id}/`),
  );
}

// ── Coupons ───────────────────────────────────────────────

export function useCoupons(
  params: { search?: string; status?: string; page?: number },
  enabled = true,
) {
  return useQuery({
    queryKey: [...KEY, 'coupons', params],
    queryFn: () =>
      http.get<PagedResponse<Coupon>>('/promotions/admin/coupons/', { params: { ...params } }),
    enabled,
  });
}

export function useSaveCoupon() {
  return usePricingMutation(({ id, body }: { id?: string; body: Record<string, unknown> }) =>
    id
      ? http.patch<Coupon>(`/promotions/admin/coupons/${id}/`, body)
      : http.post<Coupon>('/promotions/admin/coupons/', body),
  );
}

export function useDeleteCoupon() {
  return usePricingMutation((id: string) =>
    http.delete<void>(`/promotions/admin/coupons/${id}/`),
  );
}

// ═══════════════════════════════════════════════════════════
//  The coupon redemption log
// ═══════════════════════════════════════════════════════════

export interface CouponRedemption {
  id: string;
  coupon: string;
  coupon_code: string;
  user: string | null;
  user_email: string | null;
  reference_type: string;
  reference_id: string;
  discount_amount: string;
  is_cancelled: boolean;
  cancelled_at: string | null;
  created_at: string;
}

/**
 * Who redeemed the coupon, when, and for how much.
 *
 * ⚠️  **Cancelled ones are excluded by default and requested explicitly.**
 *
 *     The log keeps the use of a cancelled order and marks it; including it in
 *     the default count makes "redeemed 300 times" cover a hundred orders that
 *     shipped nothing — and the decision to extend the campaign is built on that figure.
 */
export function useCouponRedemptions(params: {
  coupon?: string;
  cancelled?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ['pricing', 'redemptions', params],
    queryFn: () =>
      http.get<PagedResponse<CouponRedemption>>('/promotions/admin/redemptions/', {
        params: { ...params },
      }),
  });
}
