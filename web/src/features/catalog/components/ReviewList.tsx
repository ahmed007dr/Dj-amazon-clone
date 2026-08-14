import { useTranslation } from 'react-i18next';

import { Badge } from '@/shared/ui/Badge';
import { formatDate } from '@/shared/utils/format';

import { useProductReviews } from '../hooks';

import { StarRating } from './StarRating';

import './ReviewList.css';

/**
 * تقييمات المنتج.
 *
 * ⚠️  «مشترٍ موثّق» شارة لا نص.
 *
 *     هي أهم إشارة ثقة في الصفحة: تقييم من اشترى فعلًا يزن أضعاف
 *     تقييم من مرّ. دفنها في نص رمادي يهدرها.
 */
export function ReviewList({ slug }: { slug: string }) {
  const { t, i18n } = useTranslation();
  const { data: reviews, isPending } = useProductReviews(slug);

  if (isPending) return null;

  if (!reviews || reviews.length === 0) {
    return <p className="muted">{t('catalog.noReviews')}</p>;
  }

  return (
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

          <p className="review__date muted">{formatDate(review.created_at, i18n.language)}</p>
        </li>
      ))}
    </ul>
  );
}
