/**
 * حالة السلة.
 *
 * ⚠️  **لا تحديث تفاؤلي ولا حساب محلي للإجماليات.**
 *
 *     يبدو التحديث التفاؤلي تحسينًا، لكن الخادم يعيد التسعير في
 *     كل استجابة: الضريبة والشحن وسقف الكوبون وأسعار الكميات كلها
 *     تتغيّر مع تغيّر الكمية. الرقم المحلي سيختلف عن الحقيقي، وسيرى
 *     العميل مبلغًا ثم مبلغًا آخر بعد جزء من الثانية.
 *
 *     الخادم يعيد اللقطة كاملة، والواجهة تكتبها في الكاش مباشرةً.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';
import type { CartQuery, CartSnapshot } from './types';

export const CART_KEY = ['cart'] as const;

export function useCart(params: CartQuery = {}) {
  return useQuery({
    queryKey: [...CART_KEY, params],
    queryFn: () => api.getCart(params),
    // ⚠️  السلة تتغيّر بفعل المستخدم لا بمرور الوقت — لكن مخزون
    //     الأصناف فيها يتغيّر بفعل مشترين آخرين.
    staleTime: 30 * 1000,
  });
}

/**
 * كل عمليات السلة تكتب اللقطة العائدة في الكاش.
 *
 * ⚠️  الكتابة المباشرة لا `invalidate`.
 *
 *     الإبطال يطلق نداءً ثانيًا لبيانات وصلت للتوّ — أي مضاعفة
 *     النداءات على أكثر شاشة تفاعلًا في المتجر.
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

// ⚠️  `void` لا `undefined` كوسيط: `useMutation` يشترط تمرير وسيط
//     حين يكون النوع `undefined`، فيصير `mutate()` بلا وسيط خطأ
//     في وقت الترجمة على أبسط عملية في السلة.
export const useRemoveCoupon = () => useCartMutation<void>(() => api.removeCoupon());

export const useClearCart = () => useCartMutation<void>(() => api.clearCart());

export const useAddBundle = () =>
  useCartMutation((args: { bundle: string; essentialsOnly?: boolean }) =>
    api.addBundle(args.bundle, args.essentialsOnly ?? false),
  );
