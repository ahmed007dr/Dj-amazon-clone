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
