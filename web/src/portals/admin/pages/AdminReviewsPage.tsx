import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminReviews,
  useModerateReview,
  type AdminReview,
} from '@/features/reviews/api';
import { StarRating } from '@/features/catalog/components/StarRating';
import { isApiError } from '@/shared/http/errors';
import { PageHeader } from '@/shared/layouts/PageHeader';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { Modal } from '@/shared/ui/Modal';
import { Pagination } from '@/shared/ui/Pagination';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { StatusTabs } from '@/shared/ui/StatusTabs';
import { useToast } from '@/shared/ui/useToast';
import { formatDate } from '@/shared/utils/format';

import './AdminReviewsPage.css';

/**
 * Review moderation.
 *
 * ⚠️  **Cards, not a table.**
 *
 *     The decision here is taken on **text** read in full: "is this decent and
 *     useful?". A table truncates the text to one line, so approving becomes a
 *     press with no reading — which is exactly what moderation exists to prevent.
 *
 * ⚠️  And the default is **pending**: they alone await an action. The approved
 *     ones are read for review, not for work.
 */
export function AdminReviewsPage() {
  const { t, i18n } = useTranslation();
  const { notify } = useToast();

  const [status, setStatus] = useState('PENDING');
  const [page, setPage] = useState(1);
  const [rejecting, setRejecting] = useState<AdminReview | null>(null);
  const [reason, setReason] = useState('');

  const query = useAdminReviews({ status, page });
  const moderate = useModerateReview();

  const fail = (error: unknown) =>
    notify(isApiError(error) ? error.displayMessage : t('state.errorTitle'), 'danger');

  const approve = (review: AdminReview) =>
    moderate.mutate(
      { id: review.id, approved: true },
      { onSuccess: () => notify(t('reviews.approved'), 'success'), onError: fail },
    );

  const confirmReject = () => {
    if (!rejecting) return;
    moderate.mutate(
      { id: rejecting.id, approved: false, reason },
      {
        onSuccess: () => {
          notify(t('reviews.rejectedDone'), 'success');
          setRejecting(null);
          setReason('');
        },
        onError: fail,
      },
    );
  };

  const reviews = query.data?.results ?? [];

  return (
    <>
      <PageHeader title={t('nav.reviews')} description={t('reviews.moderationHint')} />

      <StatusTabs
        options={[
          {
            value: 'PENDING',
            label: t('reviews.pending'),
            ...(status === 'PENDING' && query.data ? { count: query.data.count } : {}),
          },
          { value: 'APPROVED', label: t('reviews.approvedTab') },
          { value: 'REJECTED', label: t('reviews.rejected') },
        ]}
        value={status}
        onChange={(next) => {
          setStatus(next);
          setPage(1);
        }}
      />

      {query.isPending ? <Spinner /> : null}

      {!query.isPending && reviews.length === 0 ? (
        <StateMessage
          icon="✓"
          title={t('reviews.queueEmpty')}
          body={t('reviews.queueEmptyBody')}
        />
      ) : null}

      <ul className="moderation">
        {reviews.map((review) => (
          <li key={review.id} className="moderation__item">
            <div className="moderation__head">
              <StarRating value={review.rating} />
              <strong>{review.user_email}</strong>
              {review.is_verified_purchase ? (
                // ⚠️  "Verified buyer" changes the weight of the decision: a review from
                //     someone who actually bought is read more carefully before being rejected.
                <Badge tone="success">{t('catalog.verifiedPurchase')}</Badge>
              ) : null}
              <span className="moderation__date muted">
                {formatDate(review.created_at, i18n.language)}
              </span>
            </div>

            <p className="moderation__product muted">
              <code style={{ direction: 'ltr' }}>{review.product_sku}</code> —{' '}
              {review.product_name}
            </p>

            {review.title ? <p className="moderation__title">{review.title}</p> : null}
            {/* The full text with no truncation — it is the subject of the decision */}
            {review.body ? <p className="moderation__body">{review.body}</p> : null}

            {review.status === 'REJECTED' && review.moderation_reason ? (
              <p className="moderation__reason">
                {t('reviews.rejectionReason')}: {review.moderation_reason}
              </p>
            ) : null}

            {review.status === 'PENDING' ? (
              <div className="moderation__actions">
                <Button size="sm" loading={moderate.isPending} onClick={() => approve(review)}>
                  {t('reviews.approve')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRejecting(review)}>
                  {t('reviews.reject')}
                </Button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {query.data ? (
        <Pagination page={query.data.page} pages={query.data.pages} onChange={setPage} />
      ) : null}

      <Modal
        open={rejecting !== null}
        onClose={() => {
          setRejecting(null);
          setReason('');
        }}
        title={t('reviews.rejectTitle')}
        footer={
          <>
            <Button
              variant="danger"
              loading={moderate.isPending}
              disabled={reason.trim().length < 3}
              onClick={confirmReject}
            >
              {t('reviews.reject')}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setRejecting(null);
                setReason('');
              }}
            >
              {t('common.cancel')}
            </Button>
          </>
        }
      >
        {/* ⚠️  The reason is mandatory — the server enforces it. A rejection with no
            reason cannot be explained to the customer, so they rewrite the same
            text assuming something broke. */}
        <p>{t('reviews.rejectReasonHint')}</p>
        <textarea
          className="moderation__reason-input"
          rows={3}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label={t('reviews.rejectionReason')}
        />
      </Modal>
    </>
  );
}
