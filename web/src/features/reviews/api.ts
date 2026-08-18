import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
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
      // ⚠️  والتقييم المجمَّع معها: كاتب المراجعة ينظر إلى المتوسط
      //     مباشرةً بعد الإرسال، ورقمٌ لم يتحرّك يُقرأ «لم تُحفظ».
      void queryClient.invalidateQueries({ queryKey: ['reviews', 'rating'] });
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

// ═══════════════════════════════════════════════════════════
//  الأدمن — المراجعة
// ═══════════════════════════════════════════════════════════

export interface AdminReview {
  id: string;
  product: string;
  product_sku: string;
  product_name: string;
  user: string;
  user_email: string;
  rating: number;
  title: string;
  body: string;
  status: ReviewStatus;
  is_verified_purchase: boolean;
  helpful_count: number;
  moderation_reason?: string;
  created_at: string;
}

export function useAdminReviews(params: { status?: string; page?: number }) {
  return useQuery({
    queryKey: ['admin', 'reviews', params],
    queryFn: () =>
      http.get<PagedResponse<AdminReview>>('/reviews/admin/', { params: { ...params } }),
    staleTime: 30 * 1000,
  });
}

/**
 * اعتماد مراجعة أو رفضها.
 *
 * ⚠️  **سبب الرفض إلزامي** — الخادم يفرضه.
 *
 *     الرفض بلا سبب لا يُشرح للعميل، فيعيد كتابة نفس النص ظنًّا
 *     أن شيئًا تعطّل. والسبب هو ما يجعل الرفض قابلًا للتصحيح.
 *
 * ⚠️  والاعتماد يعيد حساب متوسط المنتج على الخادم — ولذلك يُبطَل
 *     الكتالوج معه، وإلا بقيت النجوم القديمة على بطاقة المنتج.
 */
export function useModerateReview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      http.post(`/reviews/admin/${id}/moderate/`, { approved, ...(reason ? { reason } : {}) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'reviews'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}
