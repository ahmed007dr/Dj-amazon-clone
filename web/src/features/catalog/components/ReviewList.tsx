import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { useMyReviews, useToggleHelpful } from '@/features/reviews/api';
import { ReviewForm } from '@/features/reviews/components/ReviewForm';
import { isApiError } from '@/shared/http/errors';
import { Alert } from '@/shared/ui/Alert';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

import { useProductReviews } from '../hooks';

import { useProductRating } from '../hooks';

import { StarRating } from './StarRating';

import './ReviewList.css';

/**
 * تقييمات المنتج — قراءةً وكتابةً.
 *
 * ⚠️  «مشترٍ موثّق» شارة لا نص.
 *
 *     هي أهم إشارة ثقة في الصفحة: تقييم من اشترى فعلًا يزن أضعاف
 *     تقييم من مرّ. دفنها في نص رمادي يهدرها.
 *
 * ⚠️  و**تقييمي يظهر لي ولو كان معلّقًا** — من قائمة منفصلة.
 *
 *     القائمة العامة تعرض المعتمد وحده، فكان المستخدم يرسل تقييمه
 *     ثم لا يجده فيعيد كتابته، فيصطدم بـ«لديك تقييم بالفعل» بلا
 *     أن يفهم أين ذهب الأول.
 */
export function ReviewList({ slug, productId }: { slug: string; productId?: string }) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const { user } = useAuth();

  const { data: reviews, isPending } = useProductReviews(slug);

  // ⚠️  **التقييم المجمَّع يُجلب مستقلًا عن تفاصيل المنتج.**
  //
  //     صفحة المنتج تحمل `rating` مضمَّنًا بمهلة خمس دقائق؛ فمن
  //     يكتب مراجعته الآن يرى متوسطًا لا يشمله حتى تنتهي المهلة،
  //     ويظنّ أن مراجعته ضاعت. هذه النقطة خفيفة وتُبطَل مع كل
  //     كتابة، فيتحرّك الرقم أمام صاحبه.
  const rating = useProductRating(slug);
  const mine = useMyReviews(Boolean(user));
  const helpful = useToggleHelpful();

  const [writing, setWriting] = useState(false);

  const myReview = productId
    ? (mine.data ?? []).find((review) => review.product === productId)
    : undefined;

  if (isPending) return null;

  const vote = (id: string) =>
    helpful.mutate(id, {
      onError: (error) =>
        notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger'),
    });

  return (
    <>
      {/* ⚠️  المتوسط الحيّ فوق قائمة المراجعات: هو ما يبحث عنه
          القارئ قبل أن يقرأ نصًّا واحدًا. */}
      {rating.data && rating.data.count > 0 ? (
        <div className="review-summary">
          <StarRating value={Number(rating.data.average)} count={rating.data.count} />
        </div>
      ) : null}

      {/* ── الكتابة ─────────────────────────────── */}
      {!user ? (
        <Alert tone="info">
          <Link to="/login">{t('reviews.signInToWrite')}</Link>
        </Alert>
      ) : myReview && !writing ? (
        <div className="review-mine">
          <div className="review-mine__head">
            <StarRating value={myReview.rating} />
            <strong>{t('reviews.yours')}</strong>
            {myReview.status === 'PENDING' ? (
              <Badge tone="warning">{t('reviews.pending')}</Badge>
            ) : myReview.status === 'REJECTED' ? (
              <Badge tone="danger">{t('reviews.rejected')}</Badge>
            ) : null}
          </div>
          {myReview.body ? <p className="review-mine__body">{myReview.body}</p> : null}
          <Button size="sm" variant="ghost" onClick={() => setWriting(true)}>
            {t('common.edit')}
          </Button>
        </div>
      ) : writing || (user && !myReview) ? (
        productId ? (
          writing || !myReview ? (
            <ReviewForm
              key={myReview?.id ?? 'new'}
              productId={productId}
              existing={myReview}
              {...(writing ? { onDone: () => setWriting(false) } : {})}
            />
          ) : null
        ) : null
      ) : null}

      {/* ── القائمة ─────────────────────────────── */}
      {!reviews || reviews.length === 0 ? (
        <p className="muted">{t('catalog.noReviews')}</p>
      ) : (
        <ul className="review-list">
          {reviews.map((review) => (
            <li key={review.id} className="review">
              <div className="review__head">
                <StarRating value={review.rating} />
                <strong className="review__author">{review.author}</strong>
                {review.is_verified_purchase ? (
                  <Badge tone="success">{t('catalog.verifiedPurchase')}</Badge>
                ) : null}
              </div>

              {review.title ? <p className="review__title">{review.title}</p> : null}
              {review.body ? <p className="review__body">{review.body}</p> : null}

              <div className="review__foot">
                <span className="review__date muted">
                  {formatDate(review.created_at, i18n.language)}
                </span>

                {/* ⚠️  لا زر على تقييمي: الخادم يردّ ٤٠٣ على التصويت
                    لتقييم النفس، وإظهار زر يفشل عند الضغط تجربة سيئة. */}
                {user && !review.is_mine ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={helpful.isPending}
                    onClick={() => vote(review.id)}
                  >
                    {t('reviews.helpful', { count: review.helpful_count })}
                  </Button>
                ) : review.helpful_count > 0 ? (
                  <span className="muted">
                    {t('reviews.helpful', { count: review.helpful_count })}
                  </span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
