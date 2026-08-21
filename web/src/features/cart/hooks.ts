/**
 * Cart state.
 *
 * ⚠️  **No optimistic update and no local total.**
 *
 *     An optimistic update looks like an improvement, but the server reprices
 *     on every response: the tax, the shipping, the coupon cap and the quantity
 *     prices all change as the quantity changes. A local figure will differ from
 *     the real one, and the customer will see one amount and then another a
 *     fraction of a second later.
 *
 *     The server returns the complete snapshot, and the frontend writes it
 *     straight into the cache.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { CartQuery, CartSnapshot } from './types';

export const CART_KEY = ['cart'] as const;

export function useCart(params: CartQuery = {}) {
  return useQuery({
    queryKey: [...CART_KEY, params],
    queryFn: () => api.getCart(params),
    // ⚠️  The cart changes through the user's actions, not with time — but the
    //     stock of the items in it changes through other buyers' actions.
    staleTime: 30 * 1000,
  });
}

/**
 * Every cart operation writes the returned snapshot into the cache.
 *
 * ⚠️  A direct write rather than `invalidate`.
 *
 *     Invalidating fires a second call for data that has just arrived — that
 *     is, doubling the calls on the most interactive screen in the store.
 */
function useCartMutation<TArgs>(mutationFn: (args: TArgs) => Promise<CartSnapshot>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onSuccess: (snapshot) => {
      queryClient.setQueriesData<CartSnapshot>({ queryKey: CART_KEY }, snapshot);
    },
  });
}

export const useAddToCart = () =>
  useCartMutation((args: { product: string; variant?: string; quantity?: number }) =>
    api.addLine(args),
  );

export const useSetLineQuantity = () =>
  useCartMutation((args: { lineId: string; quantity: number }) =>
    api.setLineQuantity(args.lineId, args.quantity),
  );

export const useRemoveLine = () => useCartMutation((lineId: string) => api.removeLine(lineId));

export const useApplyCoupon = () => useCartMutation((code: string) => api.applyCoupon(code));

// ⚠️  `void`, not `undefined`, as the argument: `useMutation` requires an
//     argument to be passed when the type is `undefined`, so `mutate()` with no
//     argument becomes a compile-time error on the simplest cart operation.
export const useRemoveCoupon = () => useCartMutation<void>(() => api.removeCoupon());

export const useClearCart = () => useCartMutation<void>(() => api.clearCart());

/**
 * Adding a bundle.
 *
 * ⚠️  **It does not go through `useCartMutation`**, because its response has a
 *     different shape: `{ bundle_result, cart }`, not a cart snapshot.
 *
 *     Writing the whole response into the cache corrupts it — the screen reads
 *     `lines` and finds it missing. Here `cart` alone is written, and
 *     `bundle_result` is left to the caller to show what was skipped and why.
 */
export function useAddBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: { bundle: string; essentialsOnly?: boolean }) =>
      api.addBundle(args.bundle, args.essentialsOnly ?? false),
    onSuccess: (response) => {
      queryClient.setQueriesData<CartSnapshot>({ queryKey: CART_KEY }, response.cart);
    },
  });
}
