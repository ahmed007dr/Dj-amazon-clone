import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './adminApi';
import type { AdminOrderQuery } from './adminApi';
import type { OrderStatus } from './types';

const KEY = ['admin', 'orders'] as const;

export function useAdminOrders(query: AdminOrderQuery) {
  return useQuery({
    queryKey: [...KEY, query],
    queryFn: () => api.listAdminOrders(query),
    // ⚠️  الطلبات تصل باستمرار — شاشة تشغيلية بمهلة قصيرة
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
    // ⚠️  إبطال الكل لا كتابة صف: الانتقال يحرّك الطلب بين التبويبات
    //     ويغيّر عدّاداتها، فالقائمة كلها تغيّرت لا صفٌّ واحد.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

/**
 * ⚠️  «إكمال» ليست انتقال حالة عاديًا.
 *
 *     تُطلق حدث `order_completed` الذي تبني عليه المالية والولاء
 *     والعمولات لاحقًا — ولها نقطة نهاية منفصلة عمدًا.
 */
export function useCompleteOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.completeOrder,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}
