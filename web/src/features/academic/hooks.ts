import { useQuery } from '@tanstack/react-query';

import * as api from './api';

export function useMyBundles(enabled = true) {
  return useQuery({
    queryKey: ['academic', 'my-bundles'],
    queryFn: api.getMyBundles,
    enabled,
    // الحزم تتغيّر مع بداية الفصل الدراسي لا خلال اليوم
    staleTime: 10 * 60 * 1000,
  });
}

export function useBundle(slug: string | undefined) {
  return useQuery({
    queryKey: ['academic', 'bundle', slug],
    queryFn: () => api.getBundle(slug as string),
    enabled: Boolean(slug),
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * ⚠️  الخادم يعيد `null` بحالة `200` لغير الطلاب لا `404`.
 *
 *     ولذلك `data` قد تكون `null` بلا أن يكون هناك خطأ — والفحص
 *     يجب أن يكون على القيمة لا على `error`.
 */
export function useStudentProfile(enabled = true) {
  return useQuery({
    queryKey: ['academic', 'me'],
    queryFn: api.getMyStudentProfile,
    enabled,
    staleTime: 10 * 60 * 1000,
  });
}
