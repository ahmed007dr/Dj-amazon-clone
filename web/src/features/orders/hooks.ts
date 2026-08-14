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
 * ⚠️  عروض الشحن من الخادم عند كل تغيير محافظة.
 *
 *     الرسوم تعتمد على المنطقة والوزن وحد الشحن المجاني — وكلها
 *     تتغيّر من لوحة الأدمن. حفظها في الواجهة يجعل تعديل الأدمن
 *     بلا أثر حتى إعادة النشر.
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
 * ⚠️  طرق الدفع تُحسب من البوابات **المفعّلة الآن**.
 *
 *     الأدمن يوقف بوابة فتختفي من هنا في الطلب التالي بلا نشر.
 *     قائمة ثابتة في الواجهة تعرض بوابة موقوفة، فيختارها العميل
 *     ويفشل دفعه.
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
      // ⚠️  السلة أُفرغت في الخادم — إبقاؤها في الكاش يعرض أصنافًا
      //     اشتُريت للتوّ ويسمح بطلب ثانٍ لها.
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
