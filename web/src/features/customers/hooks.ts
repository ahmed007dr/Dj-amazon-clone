import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';

const ADDRESSES_KEY = ['customers', 'addresses'] as const;

export function useAddresses(enabled = true) {
  return useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: api.listAddresses,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateAddress() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createAddress,
    // ⚠️  إبطال لا كتابة مباشرة: إنشاء عنوان افتراضي يُلغي افتراضية
    //     عنوان آخر في الخادم، فالقائمة كلها تغيّرت لا صفٌّ واحد.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

/**
 * ⚠️  نفس سبب الإبطال في الإنشاء: تعديل عنوان قد يجعله الافتراضي
 *     فيُلغي افتراضية غيره — والقائمة كلها تغيّرت لا صفٌّ واحد.
 */
function useAddressMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

export function useUpdateAddress() {
  return useAddressMutation(
    ({ id, body }: { id: string; body: Parameters<typeof api.updateAddress>[1] }) =>
      api.updateAddress(id, body),
  );
}

/**
 * ⚠️  الحذف **ناعم على الخادم**: الطلبات السابقة تشير إلى العنوان
 *     الذي شُحنت إليه، ومحوه يجعل كل فاتورة قديمة بلا وجهة.
 */
export function useDeleteAddress() {
  return useAddressMutation(api.deleteAddress);
}

export function useSetDefaultAddress() {
  return useAddressMutation(api.setDefaultAddress);
}
