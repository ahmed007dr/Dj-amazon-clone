import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { CART_KEY } from '@/features/cart/hooks';

import * as api from './api';
import type { CheckoutPayload } from './types';

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
export function useShippingQuotes(governorate: string, subtotal: string) {
  return useQuery({
    queryKey: ['shipping', 'quotes', governorate, subtotal],
    queryFn: () => api.getShippingQuotes(governorate, subtotal),
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

export function useCancelOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: { id: string; reason: string }) => api.cancelOrder(args.id, args.reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['orders'] }),
  });
}
