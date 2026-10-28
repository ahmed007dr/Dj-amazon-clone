import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { CART_KEY } from '@/features/cart/hooks';
import { clearGuestCartSession } from '@/shared/http/guestSession';

import * as api from './api';
import type { CheckoutPayload, GuestCheckoutPayload } from './types';

export function useMyOrders() {
  return useQuery({
    queryKey: ['orders', 'mine'],
    queryFn: api.listMyOrders,
    staleTime: 60 * 1000,
  });
}

export function useOrder(id: string | undefined) {
  return useQuery({
    queryKey: ['orders', 'detail', id],
    queryFn: () => api.getOrder(id as string),
    enabled: Boolean(id),
  });
}

/**
 * ⚠️  The shipping quotes come from the server on every governorate change.
 *
 *     The fees depend on the zone, the weight and the free-shipping threshold —
 *     all of which are changed from the admin panel. Holding them in the
 *     frontend makes the admin's edit take no effect until redeployment.
 */
export function useShippingQuotes(governorate: string, subtotal: string, eligibleAmount: string) {
  return useQuery({
    queryKey: ['shipping', 'quotes', governorate, subtotal, eligibleAmount],
    queryFn: () => api.getShippingQuotes(governorate, subtotal, eligibleAmount),
    enabled: governorate.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * ⚠️  The payment methods are computed from the gateways **enabled right now**.
 *
 *     The admin disables a gateway and it disappears from here on the next
 *     request, with no deployment. A fixed list in the frontend shows a
 *     disabled gateway, so the customer chooses it and their payment fails.
 */
export function usePaymentMethods(amount: string) {
  return useQuery({
    queryKey: ['payments', 'methods', amount],
    queryFn: () => api.getPaymentMethods({ channel: 'ONLINE', amount }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CheckoutPayload) => api.checkout(payload),
    onSuccess: () => {
      // ⚠️  The cart was emptied on the server — keeping it in the cache displays items
      //     that were just bought and allows a second order for them.
      void queryClient.invalidateQueries({ queryKey: CART_KEY });
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
}

// ═══════════════════════════════════════════════════════════
//  Guest checkout
// ═══════════════════════════════════════════════════════════

/**
 * Placing an order without an account.
 *
 * ⚠️  The cart session is **rotated** on success.
 *
 *     The server converted the cart behind this key; keeping the key means the
 *     next product the visitor adds lands in a fresh cart under the *same*
 *     identifier — harmless, but it also means the old key (now sitting in the
 *     browser's history of requests) keeps naming a live cart. A new key per
 *     purchase keeps "one browser, one basket" true.
 */
export function useGuestCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GuestCheckoutPayload) => api.guestCheckout(payload),
    onSuccess: () => {
      clearGuestCartSession();
      void queryClient.invalidateQueries({ queryKey: CART_KEY });
    },
  });
}

export function guestOrderKey(token: string | undefined) {
  return ['orders', 'guest', token] as const;
}

export function useGuestOrder(token: string | undefined) {
  return useQuery({
    queryKey: guestOrderKey(token),
    queryFn: () => api.getGuestOrder(token as string),
    enabled: Boolean(token),
    // ⚠️  A 404 / 410 on a link is final: retrying a tampered or expired token
    //     three times only delays the explanation.
    retry: false,
  });
}

export function useCancelGuestOrder(token: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reason: string) => api.cancelGuestOrder(token as string, reason),
    // The response is the order in its cancelled state — written straight in
    onSuccess: (order) => {
      queryClient.setQueryData(guestOrderKey(token), order);
    },
  });
}

export function useLookupGuestOrder() {
  return useMutation({
    mutationFn: (args: { orderNumber: string; phone: string }) =>
      api.lookupGuestOrder(args.orderNumber, args.phone),
  });
}

export function useCancelOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: { id: string; reason: string }) => api.cancelOrder(args.id, args.reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orders'] }),
  });
}
