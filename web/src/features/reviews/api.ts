import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { PagedResponse } from '@/features/orders/adminApi';
import { http } from '@/shared/http';
import type { CursorPage, Review } from '@/features/catalog/types';

/**
 * ⚠️  A review always starts **pending**.
 *
 *     The server enforces it and accepts no `status` from the client — otherwise
 *     everyone would publish their own review, bypassing moderation. And the
 *     frontend says so explicitly after submission rather than leaving the user
 *     to hunt for their review on the page.
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
 * My reviews — including the pending and the rejected.
 *
 * ⚠️  A list separate from the product's reviews: the latter shows only what is
 *     approved, so the user cannot find their review in it after submitting and
 *     assumes it was lost.
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
 * ⚠️  Invalidate **the product's reviews, my reviews and the product itself**.
 *
 *     Deleting recomputes the average rating on the server, so the product card
 *     and its stars go stale with every write. Invalidating one list leaves the
 *     old average beside the new review.
 */
function useReviewMutation<TArgs, TResult>(run: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['catalog', 'reviews'] });
      void queryClient.invalidateQueries({ queryKey: MINE_KEY });
      void queryClient.invalidateQueries({ queryKey: ['catalog', 'product'] });
      // ⚠️  And the aggregated rating with them: whoever wrote the review looks at
      //     the average straight after submitting, and a figure that has not moved reads as "it was not saved".
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
 * The "helpful" vote — **a toggle, not an increment**.
 *
 * ⚠️  The server returns `voted` and `helpful_count` together: the first for the
 *     button's state and the second for the counter. Deriving the counter
 *     locally by incrementing drifts from the server at the first vote from
 *     another window.
 */
export function useToggleHelpful() {
  return useReviewMutation((id: string) =>
    http.post<{ voted: boolean; helpful_count: number }>(`/reviews/${id}/helpful/`),
  );
}

// ═══════════════════════════════════════════════════════════
//  Admin — moderation
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
 * Approving or rejecting a review.
 *
 * ⚠️  **The rejection reason is mandatory** — the server enforces it.
 *
 *     A rejection with no reason cannot be explained to the customer, so they
 *     rewrite the same text assuming something broke. And the reason is what
 *     makes the rejection correctable.
 *
 * ⚠️  And approval recomputes the product's average on the server — which is why
 *     the catalogue is invalidated with it, or the old stars stay on the product card.
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
