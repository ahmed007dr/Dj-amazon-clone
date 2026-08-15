import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as api from './api';

const PROFILE_KEY = ['academic', 'me'] as const;

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
    queryKey: PROFILE_KEY,
    queryFn: api.getMyStudentProfile,
    enabled,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * شجرة الجامعات.
 *
 * ⚠️  `staleTime` ساعة كاملة — الجامعات والكليات لا تتغيّر خلال
 *     جلسة، والشجرة أثقل استجابة في الشاشة. إعادة جلبها عند كل
 *     تركيز نافذة هدر خالص على شبكة طالب.
 */
export function useUniversities(enabled = true) {
  return useQuery({
    queryKey: ['academic', 'universities'],
    queryFn: api.getUniversities,
    enabled,
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * ⚠️  إبطال الحزم مع الملف.
 *
 *     الحزم تُختار بالكلية والسنة، فتغيير أيٍّ منهما يجعل الحزم
 *     المعروضة حزم كلية أخرى — والطالب يشتري مستلزمات ليست له.
 */
function invalidateAcademic(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
  void queryClient.invalidateQueries({ queryKey: ['academic', 'my-bundles'] });
}

export function useCreateStudentProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createStudentProfile,
    onSuccess: () => {
      invalidateAcademic(queryClient);
    },
  });
}

export function useUpdateStudentProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.updateStudentProfile,
    onSuccess: () => {
      invalidateAcademic(queryClient);
    },
  });
}
