import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { http } from '@/shared/http';
import type { CursorPage, Review } from '@/features/catalog/types';

/**
 * ⚠️  التقييم يبدأ **معلّقًا** دائمًا.
 *
 *     الخادم يفرضه ولا يقبل `status` من العميل — وإلا نشر كلٌّ
 *     تقييمه بنفسه متجاوزًا المراجعة. والواجهة تقول ذلك صراحةً
 *     بعد الإرسال بدل أن يبحث المستخدم عن تقييمه في الصفحة.
 */
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface MyReview extends Review {
  product: string;
  status?: ReviewStatus;
}

export interface ReviewDraft {
  product: string;
  rating: number;
  title: string;
  body: string;
}

const MINE_KEY = ['reviews', 'mine'] as const;

/**
 * تقييماتي — بما فيها المعلّقة والمرفوضة.
 *
 * ⚠️  قائمة منفصلة عن تقييمات المنتج: الأخيرة تعرض المعتمد وحده،
 *     فلا يجد المستخدم تقييمه فيها بعد الإرسال ويظنّه ضاع.
 */
export function useMyReviews(enabled = true) {
  return useQuery({
    queryKey: MINE_KEY,
    queryFn: () => http.get<CursorPage<MyReview> | MyReview[]>('/reviews/mine/'),
    select: (data) => (Array.isArray(data) ? data : data.results),
    enabled,
  });
}

/**
 * ⚠️  إبطال **تقييمات المنتج وتقييماتي والمنتج نفسه**.
 *
 *     الحذف يعيد حساب متوسط التقييم على الخادم، فبطاقة المنتج
 *     ونجومها تتقادم مع كل كتابة. إبطال قائمة واحدة يترك المتوسط
 *     القديم بجوار المراجعة الجديدة.
 */
function useReviewMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['catalog', 'reviews'] });
      void queryClient.invalidateQueries({ queryKey: MINE_KEY });
      void queryClient.invalidateQueries({ queryKey: ['catalog', 'product'] });
    },
  });
}

export function useCreateReview() {
  return useReviewMutation((body: ReviewDraft) => http.post<MyReview>('/reviews/mine/', body));
}

export function useUpdateReview() {
  return useReviewMutation(({ id, body }: { id: string; body: Partial<ReviewDraft> }) =>
    http.patch<MyReview>(`/reviews/mine/${id}/`, body),
  );
}

export function useDeleteReview() {
  return useReviewMutation((id: string) => http.delete<void>(`/reviews/mine/${id}/`));
}

/**
 * التصويت «مفيدة» — **تبديل لا زيادة**.
 *
 * ⚠️  الخادم يعيد `voted` و`helpful_count` معًا: الأول لحالة الزر
 *     والثاني للعدّاد. استنتاج العدّاد محليًا بالزيادة ينحرف عن
 *     الخادم عند أول تصويت من نافذة أخرى.
 */
export function useToggleHelpful() {
  return useReviewMutation((id: string) =>
    http.post<{ voted: boolean; helpful_count: number }>(`/reviews/${id}/helpful/`),
  );
}
