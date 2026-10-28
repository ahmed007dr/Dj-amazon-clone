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
 * Product reviews — reading and writing.
 *
 * ⚠️  "Verified buyer" is a badge, not text.
 *
 *     It is the most important trust signal on the page: a review from someone
 *     who actually bought weighs many times more than one from a passer-by.
 *     Burying it in grey text wastes it.
 *
 * ⚠️  And **my own review is shown to me even while pending** — from a separate list.
 *
 *     The public list shows only what is approved, so the user submitted their
 *     review, could not find it, rewrote it, and ran into "you already have a
 *     review" with no idea where the first one went.
 */
export function ReviewList({ slug, productId }: { slug: string; productId?: string }) {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();
  const { user } = useAuth();

  const { data: reviews, isPending } = useProductReviews(slug);

  // ⚠️  **The aggregated rating is fetched independently of the product details.**
  //
  //     The product page carries `rating` embedded with a five-minute stale time;
  //     so whoever writes their review now sees an average that excludes it until
  //     that expires, and assumes their review was lost. This endpoint is light
  //     and is invalidated on every write, so the figure moves in front of its author.
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

  const average = rating.data ? Number(rating.data.average) : 0;

  return (
    <div className="reviews">
      <div className="reviews__aside">
        {/* ⚠️  The live average above the reviews list: it is what the reader
            looks for before reading a single line of text. */}
        {rating.data && rating.data.count > 0 ? (
          <div className="review-summary">
            <span className="review-summary__score">
              {new Intl.NumberFormat(i18n.language, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              }).format(average)}
            </span>
            <StarRating value={average} count={rating.data.count} />
          </div>
        ) : null}

        {/* ── Writing ─────────────────────────────── */}
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
      </div>

      {/* ── The list ────────────────────────────── */}
      <div className="reviews__main">
        {!reviews || reviews.length === 0 ? (
          <p className="reviews__empty">{t('catalog.noReviews')}</p>
        ) : (
          <ul className="review-list">
            {reviews.map((review) => (
              <li key={review.id} className="review">
                <div className="review__head">
                  {/* A decorative initial — the name is printed beside it */}
                  <span className="review__avatar" aria-hidden>
                    {Array.from(review.author.trim())[0]?.toUpperCase() ?? '·'}
                  </span>

                  <div className="review__who">
                    <div className="review__name">
                      <strong className="review__author">{review.author}</strong>
                      {review.is_verified_purchase ? (
                        <Badge tone="success">{t('catalog.verifiedPurchase')}</Badge>
                      ) : null}
                    </div>
                    <StarRating value={review.rating} />
                  </div>

                  <span className="review__date muted">
                    {formatDate(review.created_at, i18n.language)}
                  </span>
                </div>

                {review.title ? <p className="review__title">{review.title}</p> : null}
                {review.body ? <p className="review__body">{review.body}</p> : null}

                {/* ⚠️  No button on my own review: the server answers 403 to voting
                    on your own, and showing a button that fails when pressed is a bad experience. */}
                {user && !review.is_mine ? (
                  <div className="review__foot">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={helpful.isPending}
                      onClick={() => vote(review.id)}
                    >
                      {t('reviews.helpful', { count: review.helpful_count })}
                    </Button>
                  </div>
                ) : review.helpful_count > 0 ? (
                  <div className="review__foot">
                    <span className="muted">
                      {t('reviews.helpful', { count: review.helpful_count })}
                    </span>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
