import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './adminApi';
import type { AdminOrderQuery } from './adminApi';
import type { OrderStatus } from './types';

const KEY = ['admin', 'orders'] as const;

export function useAdminOrders(query: AdminOrderQuery) {
  return useQuery({
    queryKey: [...KEY, query],
    queryFn: () => api.listAdminOrders(query),
    // ⚠️  Orders arrive continuously — an operational screen with a short stale time
    staleTime: 15 * 1000,
  });
}

export function useAdminOrder(id: string | undefined) {
  return useQuery({
    queryKey: [...KEY, 'detail', id],
    queryFn: () => api.getAdminOrder(id as string),
    enabled: Boolean(id),
  });
}

export function useTransitionOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: { id: string; status: OrderStatus; note?: string }) =>
      api.transitionOrder(args.id, args.status, args.note ?? ''),
    // ⚠️  Invalidate everything rather than writing a row: the transition moves the
    //     order between tabs and changes their counters, so the whole list changed, not one row.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

/**
 * ⚠️  "Complete" is not an ordinary status transition.
 *
 *     It emits the `order_completed` event that finance, loyalty and
 *     commissions later build on — and it has a deliberately separate endpoint.
 */
export function useCompleteOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.completeOrder,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
